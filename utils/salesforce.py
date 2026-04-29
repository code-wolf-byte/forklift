import base64
import time
from functools import lru_cache
import requests
from requests.exceptions import ConnectionError as RequestsConnectionError, Timeout, RequestException

ROLE_ID_MAP = {
    "First Generation Student": 1210322592544596030,
    "International Student": 1187457897966338129,
    "First Year": 1187164746454138900,
    "Transfer Student": 1187164763189416078,
    "Graduate Student": 1187164940923060284,
    "Upperclassmen": 1205549707938766878,
    "Barrett The Honors College": 1187459588287635466,
    "Ira A. Fulton Schools of Engineering": 1187460517422444676,
    "College of Liberal Arts and Sciences": 1187460910936232099,
    "College of Global Futures": 1187459643304312852,
    "Edson College of Nursing and Health Innovation": 1187460135434588322,
    "Herberger Institute for Design and the Arts": 1187460355618779316,
    "Thunderbird School of Global Management": 1187460980247117865,
    "Mary Lou Fulton Teachers College": 1187460649798881432,
    "New College of Interdisciplinary Arts and Sciences": 1187460740316151831,
    "College of Integrative Sciences and Arts": 1187459946552492112,
    "W.P. Carey School of Business": 1187461362356605039,
    "Walter Cronkite School of Journalism and Mass Communication": 1187461060320571442,
    "Watts College of Public Service and Community Solutions": 1187461173533233192,
    "University College": 1263595373058981898,
    "Tempe": 1282464973255348366,
    "Downtown Phoenix": 1282465059431252051,
    "Polytechnic": 1282465090808971397,
    "LA Center": 1282501414433849378,
}

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

RETRY_DELAY_SECONDS = 5


class SalesforceAPI:
    """
    Lightweight wrapper around the ESB Salesforce endpoints with the student
    parsing logic lifted from main.py.
    """

    def __init__(self, client_id, client_secret, debug=False):
        self.client_id = client_id
        self.client_secret = client_secret
        self.debug = debug
        self.BASE = "https://esb.asu.edu" if debug else "https://esb-qa.asu.edu"
        self.contact_endpoint = "/api/v1/asu-sf-contact/contact"
        self.opportunity_endpoint = "/api/v1/asu-sf-opportunity/opportunity"

    @lru_cache(maxsize=1)
    def _get_headers(self):
        token = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        return {"Authorization": f"Basic {token}"}

    def make_request(self, method, endpoint, headers=None, params=None, data=None, json=None, timeout=10):
        """
        Thin wrapper over requests.request with common headers and error raising.
        """
        url = f"{self.BASE}{endpoint}"
        req_headers = headers or self._get_headers()
        response = requests.request(
            method,
            url,
            headers=req_headers,
            params=params,
            data=data,
            json=json,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    def _fetch_contact(self, asurite_id):
        return self.make_request("GET", self.contact_endpoint, params={"asurite": asurite_id})

    def _fetch_opportunities(self, contact_id):
        opportunities = []
        for career in ["Undergraduate", "Graduate"]:
            opp_data = self.make_request(
                "GET",
                self.opportunity_endpoint,
                params={"contactId": contact_id, "career": career},
            )
            if isinstance(opp_data, list):
                opportunities.extend(opp_data)
        opportunities.sort(key=lambda opp: opp.get("createdDate") or "")
        return opportunities

    @staticmethod
    def _map_program_to_college(opportunity):
        program_code = opportunity.get("collegeProgramCode") or opportunity.get("programCode")
        return PROGRAM_CODE_TO_COLLEGE_ROLE.get(program_code)

    def _enrich_from_opportunity(self, student, opportunity, allow_na_deposit=False):
        # Career + admit type
        career = opportunity.get("career")
        if career == "Undergraduate":
            student["career"] = "Undergraduate"
            opp_type = opportunity.get("type")
            if opp_type == "First Time Freshman":
                student["firstYear"] = True
                student["transfer"] = False
            elif opp_type == "Transfer":
                student["firstYear"] = False
                student["transfer"] = True
        elif career == "Graduate":
            student["career"] = "Graduate"
            student["firstYear"] = False
            student["transfer"] = False

        # Residency
        if opportunity.get("internationalStudent") is True:
            student["international"] = True
            student["inState"] = False
            student["outOfState"] = False
        else:
            student["international"] = False
            if student.get("state") == "Arizona":
                student["inState"] = True
                student["outOfState"] = False
            else:
                student["inState"] = False
                student["outOfState"] = True

        # College + program mapping
        mapped_college = self._map_program_to_college(opportunity)
        college_name = mapped_college or opportunity.get("collegeName")
        if college_name:
            student["college"] = college_name

        program_code = opportunity.get("programCode") or opportunity.get("collegeProgramCode")
        if program_code:
            student["programCode"] = program_code

        # Deposit + campus information
        deposit_paid = opportunity.get("enrollmentDepositPaid")
        if deposit_paid is None and allow_na_deposit:
            student["depositPaid"] = "N/A"
        elif deposit_paid is not None:
            student["depositPaid"] = bool(deposit_paid)

        student["campus"] = opportunity.get("currentLocation") or "N/A"
        student["termCode"] = opportunity.get("termCode")

    def get_student_info(self, asurite_id):
        """
        Fetch a student's contact + opportunity data and shape it like main.py.
        """
        contact_resp = self._fetch_contact(asurite_id)
        if "contact" not in contact_resp or not contact_resp["contact"]:
            return {"error": "No contact found"}

        contact = contact_resp["contact"][0]
        contact_id = contact.get("id")
        full_name = f"{contact.get('firstname', '')} {contact.get('lastname', '')}".strip()
        email = contact.get("email") or contact.get("leademail")
        state = contact.get("state")
        country = contact.get("country")

        opportunities = self._fetch_opportunities(contact_id)
        top_level_career = opportunities[0].get("career") if opportunities else None

        student = {
            "asurite": asurite_id,
            "name": full_name,
            "email": email,
            "state": state,
            "country": country,
            "contactId": contact_id,
            "opportunities": opportunities,
            "career": top_level_career,
        }

        for opp in opportunities:
            term_code = opp.get("termCode")
            stage = opp.get("stageName")
            if term_code in {"2267", "2261"} and stage in {"Enrolled", "Admitted"}:
                student["current"] = False
                self._enrich_from_opportunity(student, opp)
                break
            if stage in {"Admitted", "Enrolled"}:
                student["current"] = True
                self._enrich_from_opportunity(student, opp, allow_na_deposit=True)
                break

        return student


def fetch_profile_with_retry(api: SalesforceAPI, asurite_id, retry_delay=RETRY_DELAY_SECONDS):
    """
    Retry fetching a student profile when the failure is network-related.
    Mirrors main.py's resilient helper.
    """
    while True:
        try:
            return api.get_student_info(asurite_id)
        except (RequestsConnectionError, Timeout) as exc:
            print(f"[{asurite_id}] Network error: {exc}. Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
        except RequestException:
            # Non-network request problems (e.g., 4xx/5xx) should not spin forever.
            raise


# ─── Async bulk-fetch helpers (used by the analytics refresh endpoint) ─────────

import asyncio
import logging
from typing import Any

import aiohttp as _aiohttp

_logger = logging.getLogger(__name__)

_ESB_BASE = "https://esb.asu.edu"
_CONTACT_URL = f"{_ESB_BASE}/api/v1/asu-sf-contact/contact"
_OPP_URL = f"{_ESB_BASE}/api/v1/asu-sf-opportunity/opportunity"
_ASYNC_TARGET_TERM_CODES = {"2267", "2261"}


def _async_auth_header(client_id: str, client_secret: str) -> str:
    token = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    return f"Basic {token}"


def _async_is_admitted_or_enrolled(opp: dict) -> bool:
    stage = (opp.get("stageName") or "").strip().lower()
    return stage in {"enrolled", "admitted"}


def _async_parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "t"}
    return False


def _async_select_opportunity(opportunities: list[dict]) -> dict | None:
    eligible = [o for o in opportunities if isinstance(o, dict) and _async_is_admitted_or_enrolled(o)]
    for opp in eligible:
        if str(opp.get("termCode") or "") in _ASYNC_TARGET_TERM_CODES:
            return opp
    return eligible[0] if eligible else None


async def async_fetch_profile(
    session: "_aiohttp.ClientSession",
    asurite: str,
    header: str,
    sem: "asyncio.Semaphore",
) -> dict[str, Any]:
    """Return {asurite, country, state, is_international, has_opportunity, error}."""
    async with sem:
        try:
            async with session.get(
                f"{_CONTACT_URL}?asurite={asurite}",
                headers={"Authorization": header},
                timeout=_aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return {"asurite": asurite, "error": f"contact HTTP {resp.status}"}
                data = await resp.json()

            contacts = data.get("contact") or []
            if not contacts:
                return {"asurite": asurite, "error": "no contact"}

            contact = contacts[0]
            contact_id = contact.get("id")
            country = contact.get("country") or "Unknown"
            state = contact.get("state") or ""

            opportunities: list[dict] = []
            for career in ("Undergraduate", "Graduate"):
                try:
                    async with session.get(
                        f"{_OPP_URL}?contactId={contact_id}&career={career}",
                        headers={"Authorization": header},
                        timeout=_aiohttp.ClientTimeout(total=15),
                    ) as oresp:
                        if oresp.status == 200:
                            odata = await oresp.json()
                            if isinstance(odata, list):
                                opportunities.extend(odata)
                except Exception:
                    pass

            opportunities.sort(key=lambda o: str(o.get("createdDate") or ""))
            selected = _async_select_opportunity(opportunities)

            is_international = False
            if selected:
                is_international = _async_parse_bool(selected.get("internationalStudent"))
                opp_country = selected.get("country") or country
                country = opp_country if opp_country != "Unknown" else country

            return {
                "asurite": asurite,
                "country": country,
                "state": state,
                "is_international": is_international,
                "has_opportunity": selected is not None,
                "error": None,
            }

        except Exception as exc:
            return {"asurite": asurite, "error": str(exc)}


async def async_bulk_fetch_profiles(
    asuries: list[str],
    client_id: str,
    client_secret: str,
    concurrency: int = 10,
) -> list[dict[str, Any]]:
    """Fetch Salesforce profiles for a list of ASURITEs concurrently."""
    header = _async_auth_header(client_id, client_secret)
    sem = asyncio.Semaphore(concurrency)
    connector = _aiohttp.TCPConnector(limit=concurrency)
    results: list[dict] = []

    async with _aiohttp.ClientSession(connector=connector) as session:
        tasks = [async_fetch_profile(session, a, header, sem) for a in asuries]
        total = len(tasks)
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            result = await coro
            results.append(result)
            if i % 100 == 0 or i == total:
                _logger.info("Salesforce lookups: %d / %d", i, total)

    return results

