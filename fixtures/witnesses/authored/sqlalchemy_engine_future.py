"""Reviewed minimal API witness; no external or uploaded code is executed."""
import json
import warnings

observed = {"outcome": None, "result": None, "exception": None, "deprecation": False, "warnings": []}
with warnings.catch_warnings(record=True) as recorded:
    warnings.simplefilter("always")
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine("sqlite://", future=True)
        try:
            result = engine.execute(text("SELECT 1")).scalar_one()
        finally:
            engine.dispose()
        observed["outcome"] = "success"
        observed["result"] = result
    except Exception as error:
        observed["outcome"] = "exception"
        observed["exception"] = type(error).__name__
        observed["message"] = str(error)
    observed["warnings"] = [{"category": item.category.__name__, "message": str(item.message)} for item in recorded]
    observed["deprecation"] = any(issubclass(item.category, DeprecationWarning) for item in recorded)
print(json.dumps(observed, sort_keys=True))
