"""F4 Policy Module — Intent-to-TradeAction policy mapping layer.

F4 is the *only* legal conversion layer from F3 Intent to F5-executable
parameters. All position sizing, holding period, and risk constraints are
*hints* at this stage — not execution facts.

Policy layers (applied in order):
  1. GlobalBasePolicy   — Universal language-to-action baseline (rule-based)
  2. Style Archetype    — Short-term / momentum / value / cyclical style diffs
  3. Risk Preference    — Aggressive / balanced / conservative from history
  4. KOL Persona        — Individual KOL language habit corrections
  5. Content Correction — Temporary context adjustments

Current implementation: Global Base Policy only (MVP).
Style Archetype, Risk Preference, and KOL Persona are NOT yet implemented.
"""

from finer.policy.global_base import GlobalBasePolicy
from finer.policy.policy_mapper import PolicyMapper

__all__ = [
    "GlobalBasePolicy",
    "PolicyMapper",
]
