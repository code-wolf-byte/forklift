import base64
import os
from typing import Any, Dict

import requests


BASE_URL = "https://esb-qa.asu.edu/api/v1/asu-sf-contact/contact"
BASE = "https://esb-qa.asu.edu"
CONTACT_URL = f"{BASE}/api/v1/asu-sf-contact/contact"
OPP_URL = f"{BASE}/api/v1/asu-sf-opportunity/opportunity"

# These credentials are expected to be provided via environment variables.
CLIENT_ID = os.getenv("SALESFORCE_API_CLIENT_ID")
CLIENT_SECRET = os.getenv("SALESFORCE_API_CLIENT_SECRET")


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "t"}
    return False


def _created_date(opp: Dict[str, Any]) -> str:
    return str(opp.get("createdDate") or "")


def get_student_profile(asurite: str) -> Dict[str, Any]:
    """
    Look up a student's Salesforce profile by ASURITE.

    The returned structure is designed to support downstream role assignment,
    and is similar to:

    {
        "asurite": "...",
        "name": "...",
        "fullName": "...",
        "email": "...",
        "state": "...",
        "country": "...",
        "contactId": "...",
        "opportunities": [...],
        ...summary fields...
    }

    On any failure or missing configuration, a dictionary with an "error" key
    is returned.
    """
    if not CLIENT_ID or not CLIENT_SECRET:
        return {"error": "Salesforce credentials are not configured"}

    # --------------------
    # Basic Auth
    # --------------------
    token = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}

    # --------------------
    # 1. Contact Lookup
    # --------------------
    try:
        contact_resp = requests.get(
            f"{CONTACT_URL}?asurite={asurite}", headers=headers, timeout=10
        )
    except requests.RequestException as exc:
        return {"error": f"Failed to contact Salesforce for student profile: {exc}"}

    contact_resp.raise_for_status()
    contact_data = contact_resp.json()

    if "contact" not in contact_data or not contact_data["contact"]:
        return {"error": "No contact found"}

    contact = contact_data["contact"][0]
    contact_id = contact.get("id")
    first_name = contact.get("firstname", "") or ""
    last_name = contact.get("lastname", "") or ""
    full_name = f"{first_name} {last_name}".strip()

    # --------------------
    # 2. Opportunity Lookup
    # --------------------
    opportunities: list[Dict[str, Any]] = []
    for career in ["Undergraduate", "Graduate"]:
        try:
            opp_resp = requests.get(
                f"{OPP_URL}?contactId={contact_id}&career={career}",
                headers=headers,
                timeout=10,
            )
        except requests.RequestException:
            continue
        if opp_resp.status_code == 200:
            opp_data = opp_resp.json()
            if isinstance(opp_data, list):
                opportunities.extend(opp_data)

    # Sort newest first for summary fields
    opportunities.sort(key=_created_date, reverse=True)

    # Choose a primary opportunity for summary fields:
    # Prefer latest "Admitted" or "Enrolled", otherwise latest overall.
    primary_opp: Dict[str, Any] | None = None
    for opp in opportunities:
        stage = (opp.get("stageName") or "").strip().lower()
        if stage in {"admitted", "enrolled"}:
            primary_opp = opp
            break
    if primary_opp is None and opportunities:
        primary_opp = opportunities[0]

    # --------------------
    # 3. Build profile payload
    # --------------------
    email = contact.get("email")
    state = contact.get("state")
    country = contact.get("country")

    profile: Dict[str, Any] = {
        "asurite": asurite,
        "name": full_name,
        "fullName": full_name,
        "email": email,
        "state": state,
        "country": country,
        "contactId": contact_id,
        "opportunities": opportunities,
    }

    if primary_opp is not None:
        college_program_code = primary_opp.get("collegeProgramCode")
        enrollment_deposit_paid = (
            primary_opp.get("enrollmentDepositStatus") or ""
        ).strip().lower() == "paid"
        is_international = _parse_bool(primary_opp.get("internationalStudent"))
        admit_type = primary_opp.get("type")
        career = primary_opp.get("career")

        # Summary / convenience fields
        profile.update(
            {
                "college": primary_opp.get("collegeName") or "None",
                "program": primary_opp.get("academicPlanName") or "None",
                "career": career or "Unknown",
                "admitType": admit_type or "None",
                "firstTimeFreshman": bool(
                    isinstance(admit_type, str)
                    and "freshman" in admit_type.strip().lower()
                ),
                "transfer": bool(
                    isinstance(admit_type, str)
                    and "transfer" in admit_type.strip().lower()
                ),
                # Backwards-compatible / additional fields
                "collegeProgramCode": college_program_code,
                "is_international": is_international,
                "stateOfResidence": state if not is_international else None,
                "enrollmentDepositPaid": enrollment_deposit_paid,
                "stageName": primary_opp.get("stageName"),
            }
        )

    if not opportunities:
        profile["error"] = "No opportunities found"

    return profile


# --------------------
# Test
# --------------------
if __name__ == "__main__":
    result = get_student_profile("tupreti")
    print(result)
