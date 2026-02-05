"""Hard-coded mapping of logical role names to Discord role IDs.

Populate ROLE_ID_MAP with the role names and corresponding numeric IDs from
your Discord server. These IDs are used when assigning roles based on
Salesforce student profile data.
"""

from __future__ import annotations

from typing import Dict

ROLE_ID_MAP: Dict[str, int] = {
    # Special Roles
    "First Generation Student": 1210322592544596030,
    # Academic Level Roles
    "First Year": 1187164746454138900,
    "Transfer Student": 1187164763189416078,
    "Graduate Student": 1187164940923060284,
    "Upperclassmen": 1205549707938766878,
    # College Roles
    "Barrett The Honors College": 1187459588287635466,
    "College of Health Solutions": 1187459874808930474,
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
    # Campus Roles
    "Tempe": 1282464973255348366,
    "Downtown Phoenix": 1282465059431252051,
    "Polytechnic": 1282465090808971397,
    "LA Center": 1282501414433849378,
    "West Valley": 1282465131749576704,
    "Online": 1465991804993278113,
    # Residency Status Roles
    "Out of State": 1333934752490848377,
    "Arizona Resident": 1333934478887882823,
    "International Student": 1187457897966338129,
}
