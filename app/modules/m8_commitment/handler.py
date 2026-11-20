from app.web import record
from flask import Blueprint, jsonify

api = Blueprint("commitment", __name__)


@api.get("/api/commitment/<plan>")
def inspection(plan):
    result = record(plan)
    return jsonify({key: result[key] for key in ("承诺",) if key in result})
