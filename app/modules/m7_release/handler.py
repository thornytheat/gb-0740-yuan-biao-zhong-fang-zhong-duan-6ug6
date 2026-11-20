from app.modules.m7_release.service import attest
from app.web import record, repository
from flask import Blueprint, jsonify

api = Blueprint("release", __name__)


@api.get("/api/release/<plan>")
def inspection(plan):
    result = record(plan)
    return jsonify({"批次": result["批次"], "证据": attest(repository(), plan)})
