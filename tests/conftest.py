"""Root test configuration.

Importing all domain submodules here ensures that every ORM model is registered
with Base.metadata before any test fixture calls Base.metadata.create_all(). Without
this, a FK in one module can reference a table that hasn't been mapped yet.
"""

import personal_finance.domain.balance_sheet  # noqa: F401
import personal_finance.domain.goals  # noqa: F401
