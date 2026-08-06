"""
Sampling parameters that some models refuse.

Newer Claude models reject `temperature` outright — the API answers
`` `temperature` is deprecated for this model `` — while older ones still accept it. Sending it
to a model that refuses it fails the entire request, so the known families are recognized up
front and the parameter is simply not sent.

A name list alone is not enough, because the model string reaching a provider may be a
gateway's own alias for the same model, which no list can predict. So an unrecognized model
that turns out to refuse `temperature` is retried once without it and then remembered, and
subsequent calls in the same session skip it up front. Recognition keeps the normal path from
ever failing; the retry keeps an unfamiliar alias from being a dead end.

Erring toward not sending is deliberate: omitting `temperature` only means the model applies
its own default, while sending it where it is refused loses the whole call.
"""

from typing import Set

# Families known to refuse the parameter. Matched as a prefix so dated and suffixed variants
# are covered. Only families actually observed refusing it belong here - wrongly listing one
# would silently discard a temperature the user meant to set.
_FAMILIES_REJECTING_TEMPERATURE = (
    "claude-opus-5",
    "claude-fable-5",
)

_models_rejecting_temperature: Set[str] = set()


def rejects_temperature(model: str) -> bool:
    """Whether `temperature` should be left out of requests for this model."""
    if model in _models_rejecting_temperature:
        return True

    # A gateway alias often embeds the family name even when it is not an exact match.
    normalized = model.rsplit("/", 1)[-1].lower()
    return any(normalized.startswith(family) for family in _FAMILIES_REJECTING_TEMPERATURE)


def remember_temperature_rejection(model: str) -> None:
    """Record that a model refuses `temperature`, so later calls skip sending it."""
    _models_rejecting_temperature.add(model)


def is_temperature_rejection(error: Exception) -> bool:
    """
    Whether an API error is the model refusing `temperature`.

    Deliberately narrow: it must name the parameter *and* say it is unsupported, so an
    unrelated bad request is never retried.
    """
    text = str(error).lower()
    if "temperature" not in text:
        return False
    return any(
        marker in text
        for marker in ("deprecated", "not supported", "unsupported", "not permitted")
    )


__all__ = [
    "rejects_temperature",
    "remember_temperature_rejection",
    "is_temperature_rejection",
]
