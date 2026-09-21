"""The Experience Contract as a read-only surface.

Three questions, three answers, all generated from the sources of truth that
already exist - the interface registry, the declared screen definitions and the
translation catalogs:

* ``/api/experience/contracts`` - every screen's contract: identity, navigation,
  actions, columns, filters, states, help, shortcuts, layout and the translation
  keys it needs;
* ``/api/experience/contracts/<interface_id>`` - one screen, for the inspector;
* ``/api/experience/coverage`` - what is translated, per language and per
  screen, measured from the catalogs rather than estimated.

Read-only on purpose, and the reason is the same one the registry API states:
*reading* a contract is safe, and the write side is an administrative action
that has to validate, version, preview and audit itself. That side is the
Experience Studio, and until it exists these endpoints report the current state
of the experience rather than pretending to configure it.
"""

from __future__ import annotations

import logging

from flask import jsonify, request

logger = logging.getLogger(__name__)

#: How many contracts a list response returns before it says it truncated.
DEFAULT_LIMIT = 200


def register_experience_routes(app) -> None:
    """Register the experience contract views."""

    @app.route("/api/experience/contracts", methods=["GET"])
    def experience_contracts():
        """Every screen's contract, with the counts this build produced."""
        from core.experience import contract_counts, contracts_json, screens_without_experience

        domain = request.args.get("domain")
        items = contracts_json()
        if domain:
            items = [item for item in items if item["domain"] == domain]
        declared = request.args.get("declared")
        if declared is not None:
            wanted = declared.lower() in ("1", "true", "yes")
            items = [item for item in items if item["screen"]["declared"] is wanted]

        limit = min(int(request.args.get("limit", DEFAULT_LIMIT)), 500)
        counts = contract_counts()
        return jsonify({
            "success": True,
            "counts": counts,
            "total": len(items),
            "returned": min(len(items), limit),
            "truncated": len(items) > limit,
            "contracts": items[:limit],
            # The honest gap, named rather than implied: screens with a derived
            # contract that nobody has described yet.
            "screens_without_experience": list(screens_without_experience()),
        })

    @app.route("/api/experience/contracts/<interface_id>", methods=["GET"])
    def experience_contract(interface_id: str):
        """One screen's contract, or a clear answer that it is not registered."""
        from core.experience import check_contract, contract, hardcoded_source_strings

        item = contract(interface_id)
        if item is None:
            return jsonify({
                "success": False,
                "error": "No interface is registered with that id",
                "interface_id": interface_id,
            }), 404
        return jsonify({
            "success": True,
            "contract": item.to_dict(),
            # `problems` is what the contract itself is wrong about; an empty
            # list is the normal answer for a registered interface.
            "problems": check_contract(item),
            "keys_still_keyed_by_source": list(
                hardcoded_source_strings(interface_id)),
        })

    @app.route("/api/experience/coverage", methods=["GET"])
    def experience_coverage():
        """Translation coverage, per language and per screen."""
        from core.experience import (
            coverage_counts,
            language_coverage,
            screen_coverage,
        )

        interface_id = request.args.get("interface")
        return jsonify({
            "success": True,
            "counts": coverage_counts(),
            "languages": language_coverage(),
            "screens": screen_coverage(interface_id),
        })
