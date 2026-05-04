import logging
import os
import time
from typing import Any, Dict, Iterable
import requests

from .models import StudentProfile

logger = logging.getLogger(__name__)

TOKEN_URL = "https://weblogin.asu.edu/serviceauth/oauth2/client/token"
_DEFAULT_BASE = "https://crmapi-prod.apps.asu.edu"
BASE = os.getenv("SALESFORCE_API_BASE_URL", _DEFAULT_BASE)
CONTACT_URL = f"{BASE}/v1/crm-contact/contact"
OPP_URL = f"{BASE}/v1/crm-opportunity/opportunity"

# These credentials are expected to be provided via environment variables.
CLIENT_ID = os.getenv("SALESFORCE_API_CLIENT_ID")
CLIENT_SECRET = os.getenv("SALESFORCE_API_CLIENT_SECRET")

_token_cache: dict = {}


def _get_bearer_token() -> str:
    now = time.time()
    if _token_cache.get("token") and _token_cache.get("expires_at", 0) > now + 60:
        return _token_cache["token"]
    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError("Salesforce credentials not configured")
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": (
                f"{BASE}/v1/crm-contact/contact/read:all "
                f"{BASE}/v1/crm-opportunity/opportunity/read:all"
            ),
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 3600)
    return _token_cache["token"]


# Map program codes (undergrad + graduate) to college role names.
PROGRAM_CODE_TO_COLLEGE_ROLE = {
    # College of Global Futures
    "UGGF": "College of Global Futures",
    "GRGF": "College of Global Futures",
    # College of Health Solutions
    "UGNH": "College of Health Solutions",
    "GRNH": "College of Health Solutions",
    # College of Integrative Sciences and Arts
    "UGLS": "College of Integrative Sciences and Arts",
    "GRLS": "College of Integrative Sciences and Arts",
    # Edson College of Nursing and Health Innovation
    "UGNU": "Edson College of Nursing and Health Innovation",
    "GRNU": "Edson College of Nursing and Health Innovation",
    # Herberger Institute for Design and the Arts
    "UGHI": "Herberger Institute for Design and the Arts",
    "GRHI": "Herberger Institute for Design and the Arts",
    # Ira A. Fulton Schools of Engineering
    "UGES": "Ira A. Fulton Schools of Engineering",
    "GRES": "Ira A. Fulton Schools of Engineering",
    # Mary Lou Fulton Teachers College
    "UGTE": "Mary Lou Fulton Teachers College",
    "GRTE": "Mary Lou Fulton Teachers College",
    # New College of Interdisciplinary Arts and Sciences
    "UGAS": "New College of Interdisciplinary Arts and Sciences",
    "GRAS": "New College of Interdisciplinary Arts and Sciences",
    # The College of Liberal Arts and Sciences
    "UGLA": "College of Liberal Arts and Sciences",
    "GRLA": "College of Liberal Arts and Sciences",
    # Thunderbird School of Global Management
    "UGTB": "Thunderbird School of Global Management",
    "GRTB": "Thunderbird School of Global Management",
    # University College
    "UGUC": "University College",
    # W. P. Carey School of Business
    "UGBA": "W.P. Carey School of Business",
    "GRBA": "W.P. Carey School of Business",
    # Walter Cronkite School of Journalism and Mass Communication
    "UGCS": "Walter Cronkite School of Journalism and Mass Communication",
    "GRCS": "Walter Cronkite School of Journalism and Mass Communication",
    # Watts College of Public Service and Community Solutions
    "UGPP": "Watts College of Public Service and Community Solutions",
    "GRPP": "Watts College of Public Service and Community Solutions",
    # School of Technology for Public Health
    "GRTH": "School of Technology for Public Health",
}

TARGET_TERM_CODES = {"2267", "2261"}


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "t"}
    return False


def _created_date(opp: Dict[str, Any]) -> str:
    return str(opp.get("createdDate") or "")

def _is_admitted_or_enrolled(opp: Dict[str, Any]) -> bool:
    stage = (opp.get("stageName") or "").strip().lower()
    return stage in {"enrolled", "admitted"}


def _eligible_opportunities(
    opportunities: Iterable[Dict[str, Any]],
) -> list[Dict[str, Any]]:
    return [
        opp
        for opp in opportunities
        if isinstance(opp, dict) and _is_admitted_or_enrolled(opp)
    ]


def _select_opportunity(
    opportunities: list[Dict[str, Any]],
) -> tuple[Dict[str, Any] | None, bool | None]:
    """
    Select the opportunity to derive summary status fields.

    Returns (selected_opp, is_current_student) where is_current_student is:
    - False for target term codes (incoming/current term)
    - True for admitted/enrolled non-target term codes
    - None if no eligible opportunity found
    """
    eligible = _eligible_opportunities(opportunities)

    for opp in eligible:
        term_code = str(opp.get("termCode") or "")
        if term_code in TARGET_TERM_CODES:
            return opp, False

    if eligible:
        return eligible[0], True

    return None, None


def _deposit_paid_from_opportunity(opp: Dict[str, Any]) -> bool:
    if _parse_bool(opp.get("enrollmentDepositPaid")):
        return True
    status = (opp.get("enrollmentDepositStatus") or "").strip().lower()
    return status == "paid"


def get_student_profile(asurite: str) -> StudentProfile | None:
    """
    Look up a student's Salesforce profile by ASURITE.

    Returns a StudentProfile on success, or None when credentials are missing,
    the API is unreachable, no contact is found, or no opportunities exist.
    """
    if not CLIENT_ID or not CLIENT_SECRET:
        logger.warning("Salesforce credentials are not configured")
        return None

    try:
        bearer = _get_bearer_token()
    except Exception as exc:
        logger.warning("Failed to obtain Salesforce OAuth token: %s", exc)
        return None

    headers = {"Authorization": f"Bearer {bearer}"}

    # --------------------
    # 1. Contact Lookup
    # --------------------
    try:
        contact_resp = requests.get(
            f"{CONTACT_URL}?asurite={asurite}", headers=headers, timeout=10
        )
    except requests.RequestException as exc:
        logger.warning("Failed to contact Salesforce for student profile for %s: %s", asurite, exc)
        return None

    contact_resp.raise_for_status()
    contact_data = contact_resp.json()

    if "contact" not in contact_data or not contact_data["contact"]:
        logger.info("No Salesforce contact found for %s", asurite)
        return None

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

    # Sort oldest first to match legacy selection behavior.
    opportunities.sort(key=_created_date)

    # Choose an opportunity for summary fields.
    selected_opp, is_current_student = _select_opportunity(opportunities)

    # --------------------
    # 3. Build profile payload
    # --------------------
    email = contact.get("email")
    state = contact.get("state")
    country = contact.get("country")

    # Compute residency from contact state (used as fallback or when no opportunity)
    state_normalized = (state or "").strip().lower()

    profile: Dict[str, Any] = {
        "asurite": asurite,
        "name": full_name,
        "fullName": full_name,
        "email": email,
        "state": state,
        "country": country,
        "contactId": contact_id,
        "opportunities": opportunities,
        # Default residency from contact state (may be overridden by opportunity data)
        "inState": state_normalized in {"arizona", "az"},
        "outOfState": bool(state_normalized and state_normalized not in {"arizona", "az"}),
    }

    if selected_opp is not None:
        college_program_code = selected_opp.get("collegeProgramCode") or selected_opp.get(
            "programCode"
        )
        is_international = _parse_bool(selected_opp.get("internationalStudent"))
        admit_type = selected_opp.get("type")
        career = selected_opp.get("career")
        # Override residency if international student
        in_state = (state_normalized in {"arizona", "az"}) if not is_international else False
        out_of_state = bool(not in_state and state_normalized) if not is_international else False

        # Summary / convenience fields
        profile.update(
            {
                "college": PROGRAM_CODE_TO_COLLEGE_ROLE.get(
                    college_program_code, selected_opp.get("collegeName") or "N/A"
                ),
                "program": selected_opp.get("academicPlanName") or "None",
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
                "enrollmentDepositPaid": _deposit_paid_from_opportunity(selected_opp),
                "stageName": selected_opp.get("stageName"),
                # Fields used by role derivation / status displays
                "current": is_current_student,
                "firstYear": False,
                "depositPaid": _deposit_paid_from_opportunity(selected_opp),
                "international": is_international,
                "inState": in_state,
                "outOfState": out_of_state,
                "campus": selected_opp.get("currentLocation") or "N/A",
                "locationName": selected_opp.get("locationName")
                or selected_opp.get("currentLocation")
                or "N/A",
                "termCode": selected_opp.get("termCode"),
                "selectedOpportunity": selected_opp,
            }
        )
        if career and career.lower() == "undergraduate":
            if isinstance(admit_type, str) and "transfer" in admit_type.lower():
                profile["firstYear"] = False
                profile["transfer"] = True
                profile["type"] = "Transfer"
            elif isinstance(admit_type, str) and "freshman" in admit_type.lower():
                profile["firstYear"] = True
                profile["transfer"] = False
                profile["type"] = "First Time Freshman"
        elif career and career.lower() == "graduate":
            profile["firstYear"] = False
            profile["transfer"] = False
            profile["type"] = "Masters"

    if not opportunities:
        logger.info("No Salesforce opportunities found for %s", asurite)
        return None

    return StudentProfile.model_validate(profile)
