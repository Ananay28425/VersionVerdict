"""Reviewed minimal API witness; no external or uploaded code is executed."""
import json
import warnings

observed = {"outcome": None, "result": None, "exception": None, "deprecation": False, "warnings": []}
with warnings.catch_warnings(record=True) as recorded:
    warnings.simplefilter("always")
    try:
        from pydantic import BaseModel
        class User(BaseModel):
            id: int
        result = User.parse_obj({"id": "7"}).id
        observed["outcome"] = "success"
        observed["result"] = result
    except Exception as error:
        observed["outcome"] = "exception"
        observed["exception"] = type(error).__name__
        observed["message"] = str(error)
    observed["warnings"] = [{"category": item.category.__name__, "message": str(item.message)} for item in recorded]
    observed["deprecation"] = any(issubclass(item.category, DeprecationWarning) for item in recorded)
print(json.dumps(observed, sort_keys=True))
