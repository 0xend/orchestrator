from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.agents.providers import LLMProvider, create_provider

if TYPE_CHECKING:
    from app.config import Settings


@dataclass(slots=True)
class ModelOption:
    provider: str
    model_id: str
    display_name: str


def get_available_models(settings: Settings) -> list[ModelOption]:
    models: list[ModelOption] = []

    if settings.anthropic_api_key.strip():
        models.append(
            ModelOption(
                provider="anthropic",
                model_id=settings.anthropic_model,
                display_name=f"Anthropic ({settings.anthropic_model})",
            )
        )

    if settings.openai_api_key.strip():
        models.append(
            ModelOption(
                provider="openai",
                model_id=settings.openai_model,
                display_name=f"OpenAI ({settings.openai_model})",
            )
        )

    if settings.openai_compatible_api_key.strip() and settings.openai_compatible_base_url.strip():
        display = settings.openai_compatible_model or "custom"
        models.append(
            ModelOption(
                provider="openai_compatible",
                model_id=settings.openai_compatible_model,
                display_name=f"OpenAI-Compatible ({display})",
            )
        )

    return models


def resolve_provider(
    provider_name: str | None,
    model_id: str | None,
    settings: Settings,
) -> LLMProvider:
    provider = provider_name or settings.default_provider

    if provider == "anthropic":
        return create_provider(
            "anthropic",
            api_key=settings.anthropic_api_key,
            model=model_id or settings.anthropic_model,
        )
    if provider == "openai":
        return create_provider(
            "openai",
            api_key=settings.openai_api_key,
            model=model_id or settings.openai_model,
        )
    if provider == "openai_compatible":
        return create_provider(
            "openai_compatible",
            api_key=settings.openai_compatible_api_key,
            model=model_id or settings.openai_compatible_model,
            base_url=settings.openai_compatible_base_url or None,
        )
    raise ValueError(f"Unknown provider: {provider}")


def has_any_provider_key(settings: Settings) -> bool:
    return bool(
        settings.anthropic_api_key.strip()
        or settings.openai_api_key.strip()
        or settings.openai_compatible_api_key.strip()
    )


def has_provider_key(provider_name: str | None, settings: Settings) -> bool:
    provider = provider_name or settings.default_provider
    if provider == "anthropic":
        return bool(settings.anthropic_api_key.strip())
    if provider == "openai":
        return bool(settings.openai_api_key.strip())
    if provider == "openai_compatible":
        return bool(settings.openai_compatible_api_key.strip())
    return False
