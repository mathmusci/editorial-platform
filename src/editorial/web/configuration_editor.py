from __future__ import annotations

import copy
import hashlib
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from editorial.config import load_publication_config
from editorial.config.models import ProcessorConfig
from editorial.models import Article


TYPES = {
    "providers": {"rss": "RSS feed", "static": "Static articles"},
    "extractors": {"reading_time": "Reading time", "llm_summary": "LLM summary"},
    "evaluators": {
        "rule_relevance": "Rule relevance",
        "llm_relevance": "LLM relevance",
        "llm_summary_quality": "LLM summary quality",
    },
    "publishers": {"markdown": "Markdown"},
}
LLM_MODELS = {
    "ollama": ["qwen3.5:9b", "deepseek-r1:8b", "gpt-oss:20b"],
    "openai": ["gpt-4.1-mini"],
}
EDITORIAL_STATUSES = ["new", "candidate", "accepted", "rejected", "published"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def settings(entry: dict) -> dict:
    return {
        **(entry.get("settings") or {}),
        **{
            k: v
            for k, v in entry.items()
            if k not in {"type", "key", "name", "enabled", "settings"}
        },
    }


def set_setting(entry: dict, key: str, value: Any) -> None:
    target = (
        entry.get("settings", {}) if key not in entry and "settings" in entry else entry
    )
    target.pop(key, None)
    if value is not None:
        target[key] = value
    if target is entry and isinstance(entry.get("settings"), dict):
        entry["settings"].pop(key, None)


def sensitive(value: Any) -> bool:
    # URLs can contain credentials even when their field name is innocuous.
    if not isinstance(value, str) or "://" not in value:
        return False
    try:
        url = urlsplit(value)
        return bool(url.username or url.password or url.query)
    except ValueError:
        return True


@dataclass
class Draft:
    data: dict
    source: Path | None = None
    original_digest: str | None = None
    errors: dict[str, str] = field(default_factory=dict)
    revision: int = 0
    filename: str = "publication.yaml"

    @classmethod
    def open(cls, path: Path | None) -> Draft:
        if path is None:
            return cls(
                {
                    "publication": {"name": "", "description": ""},
                    "providers": [],
                    "extractors": [],
                }
            )
        path = path.resolve(strict=True)
        load_publication_config(path)
        raw = yaml.safe_load(path.read_text())
        return cls(raw, path, digest(path), filename=path.name)

    def fields(self) -> list[dict]:
        result = []

        def add(
            id,
            label,
            obj,
            key,
            kind="text",
            default="",
            choices=None,
            help=None,
            minimum=None,
            maximum=None,
            step=None,
        ):
            value = obj.get(key, default)
            hidden = sensitive(value)
            result.append(
                dict(
                    id=id,
                    label=label,
                    obj=obj,
                    key=key,
                    kind=kind,
                    value="" if hidden else value,
                    protected=hidden,
                    choices=choices,
                    help=help,
                    minimum=minimum,
                    maximum=maximum,
                    step=step,
                )
            )

        def add_llm_provider(prefix: str, config: dict) -> None:
            provider = config.get("provider")
            if not isinstance(provider, dict):
                provider = {
                    "type": provider or "fake",
                    **{
                        k: config[k]
                        for k in (
                            "model",
                            "response_text",
                            "metadata",
                            "api_key_env",
                            "base_url",
                            "organization",
                            "project",
                            "temperature",
                            "max_tokens",
                        )
                        if k in config
                    },
                }
            add(
                f"{prefix}.provider.type",
                "LLM provider",
                provider,
                "type",
                "select",
                "fake",
                ["fake", "openai", "ollama"],
            )
            for key, label, kind, default in [
                ("model", "Model", "text", ""),
                ("base_url", "Base URL", "text", ""),
                ("temperature", "Temperature", "number", 0),
                ("max_tokens", "Maximum tokens", "number", 180),
                (
                    "api_key_env",
                    "API key environment variable",
                    "text",
                    "OPENAI_API_KEY",
                ),
                ("organization", "Organisation", "text", ""),
                ("project", "Project", "text", ""),
                ("response_text", "Fake response", "textarea", ""),
            ]:
                if (
                    key in {"base_url", "temperature", "max_tokens"}
                    and provider["type"] == "fake"
                ):
                    continue
                if (
                    key in {"api_key_env", "organization", "project"}
                    and provider["type"] != "openai"
                ):
                    continue
                if key == "response_text" and provider["type"] != "fake":
                    continue
                choices = None
                if key == "model" and provider["type"] in LLM_MODELS:
                    kind = "select"
                    choices = list(LLM_MODELS[provider["type"]])
                    existing_model = provider.get("model")
                    if existing_model and existing_model not in choices:
                        choices.insert(0, existing_model)
                add(
                    f"{prefix}.provider.{key}",
                    label,
                    provider,
                    key,
                    kind,
                    default,
                    choices,
                )

        publication = self.data.setdefault("publication", {})
        add("publication.name", "Publication name", publication, "name")
        add(
            "publication.description",
            "Description",
            publication,
            "description",
            "textarea",
        )
        policy = self.data.get("editorial_policy") or {}
        for key, label, help in [
            (
                "maximum_age_days",
                "Maximum article age (days)",
                "Publication-policy metadata. This is not currently applied by the greedy optimiser.",
            ),
            (
                "maximum_articles",
                "Maximum articles",
                "Publication-policy metadata. Set the optimiser's maximum articles separately to affect selection.",
            ),
            (
                "maximum_reading_minutes",
                "Maximum reading time (minutes)",
                "Publication-policy metadata. The greedy optimiser uses its own reading-time target.",
            ),
        ]:
            add(
                f"editorial_policy.{key}",
                label,
                policy,
                key,
                "number",
                None,
                help=help,
                minimum=1,
                step=1,
            )
        eligible = policy.get("statuses_eligible_for_issue", ["accepted"])
        for status in EDITORIAL_STATUSES:
            result.append(
                dict(
                    id=f"editorial_policy.status.{status}",
                    label=status.capitalize(),
                    obj=policy,
                    key=status,
                    kind="checkbox",
                    value=status in eligible,
                    protected=False,
                    choices=None,
                    help=None,
                    minimum=None,
                    maximum=None,
                    step=None,
                )
            )

        optimisation = self.data.get("optimisation") or {}
        strategy = optimisation.get("strategy", "none")
        strategy_choices = ["none", "greedy"]
        if strategy not in strategy_choices:
            strategy_choices.insert(0, strategy)
        add(
            "optimisation.strategy",
            "Strategy",
            optimisation,
            "strategy",
            "select",
            "none",
            strategy_choices,
            "Choose Greedy to construct issue proposals. None is suitable for configurations that stop before optimisation.",
        )
        optimiser_settings = optimisation.get("settings") or {}
        for key, label, default, help, minimum, maximum, step in [
            (
                "max_articles",
                "Maximum articles",
                8,
                "Hard limit on the number of selected articles.",
                1,
                None,
                1,
            ),
            (
                "hard_minimum_relevance_score",
                "Hard minimum relevance score",
                None,
                "Exclude articles below this score. Leave blank to keep all scored candidates eligible.",
                0,
                100,
                "any",
            ),
            (
                "relevance_target_score",
                "Relevance target score",
                None,
                "Soft target. Articles below it remain eligible but incur a penalty.",
                0,
                100,
                "any",
            ),
            (
                "relevance_target_weight",
                "Relevance target weight",
                1,
                "Penalty applied for each point below the relevance target.",
                0,
                None,
                "any",
            ),
            (
                "reading_time_target_minutes",
                "Reading-time target (minutes)",
                None,
                "Soft target for total selected reading time; it is not a maximum.",
                0,
                None,
                "any",
            ),
            (
                "reading_time_weight",
                "Reading-time weight",
                3,
                "Penalty applied for each minute above or below the target.",
                0,
                None,
                "any",
            ),
            (
                "mandatory_terms_weight",
                "Topic coverage weight",
                5,
                "Reward for each configured topic represented in the selection.",
                0,
                None,
                "any",
            ),
            (
                "source_diversity_max_per_source",
                "Preferred maximum per source",
                None,
                "Soft source-diversity target. Extra articles from a source remain possible with a penalty.",
                1,
                None,
                1,
            ),
            (
                "source_diversity_weight",
                "Source-diversity weight",
                2,
                "Penalty for each selected article above the preferred per-source maximum.",
                0,
                None,
                "any",
            ),
        ]:
            add(
                f"optimisation.settings.{key}",
                label,
                optimiser_settings,
                key,
                "number",
                default,
                help=help,
                minimum=minimum,
                maximum=maximum,
                step=step,
            )
        add(
            "optimisation.settings.mandatory_terms",
            "Topics to represent (one per line)",
            optimiser_settings,
            "mandatory_terms",
            "lines",
            [],
            help="Soft coverage preference matched against article title, summary and content.",
        )
        result[-1]["value"] = "\n".join(optimiser_settings.get("mandatory_terms", []))
        for group in TYPES:
            for i, entry in enumerate(self.data.get(group, [])):
                prefix = f"{group}.{i}"
                if entry["type"] not in TYPES[group]:
                    continue
                for key, label, kind in [
                    ("name", "Display name", "text"),
                    ("key", "Processor key", "text"),
                    ("enabled", "Enabled", "checkbox"),
                ]:
                    add(
                        f"{prefix}.{key}",
                        label,
                        entry,
                        key,
                        kind,
                        True if key == "enabled" else "",
                    )
                config = settings(entry)
                if entry["type"] == "rss":
                    for key, label in [
                        ("url", "Feed URL"),
                        ("path", "Local feed path"),
                        ("source", "Source name"),
                    ]:
                        add(f"{prefix}.{key}", label, config, key)
                elif entry["type"] == "static":
                    for j, article in enumerate(config.get("articles", [])):
                        for key, label in [
                            ("title", "Title"),
                            ("url", "URL"),
                            ("source", "Source"),
                            ("published_at", "Published at"),
                            ("authors", "Authors (one per line)"),
                            ("summary", "Summary"),
                            ("content", "Content"),
                        ]:
                            add(
                                f"{prefix}.article.{j}.{key}",
                                label,
                                article,
                                key,
                                "textarea"
                                if key in {"authors", "summary", "content"}
                                else "text",
                            )
                            if key == "authors":
                                result[-1]["value"] = "\n".join(
                                    article.get("authors", [])
                                )
                elif entry["type"] == "reading_time":
                    add(
                        f"{prefix}.words_per_minute",
                        "Words per minute",
                        config,
                        "words_per_minute",
                        "number",
                        200,
                    )
                elif entry["type"] == "llm_summary":
                    add_llm_provider(prefix, config)
                elif entry["type"] == "rule_relevance":
                    for key, label in [
                        ("include", "Include terms (one per line)"),
                        ("exclude", "Exclude terms (one per line)"),
                    ]:
                        add(prefix + "." + key, label, config, key, "lines", [])
                        result[-1]["value"] = "\n".join(config.get(key, []))
                    weights = config.get("weights") or {}
                    for key, label, default in [
                        ("title", "Title weight", 5),
                        ("summary", "Summary weight", 2),
                        ("content", "Content weight", 1),
                    ]:
                        add(
                            f"{prefix}.weight.{key}",
                            label,
                            weights,
                            key,
                            "number",
                            default,
                        )
                elif entry["type"] in {"llm_relevance", "llm_summary_quality"}:
                    add(
                        prefix + ".criterion",
                        "Criterion",
                        config,
                        "criterion",
                        default=(
                            "editorial_relevance"
                            if entry["type"] == "llm_relevance"
                            else "summary_quality"
                        ),
                    )
                    if entry["type"] == "llm_summary_quality":
                        extractor_choices = [
                            extractor.get("key") or "llm_summary"
                            for extractor in self.data.get("extractors", [])
                            if extractor.get("type") == "llm_summary"
                        ]
                        extractor_choices = list(dict.fromkeys(extractor_choices))
                        existing = config.get("summary_extractor", "llm_summary")
                        if existing not in extractor_choices:
                            extractor_choices.insert(0, existing)
                        add(
                            prefix + ".summary_extractor",
                            "Summary extractor",
                            config,
                            "summary_extractor",
                            "select",
                            "llm_summary",
                            extractor_choices,
                        )
                    add_llm_provider(prefix, config)
                elif entry["type"] == "markdown":
                    add(
                        prefix + ".template",
                        "Template path",
                        config,
                        "template",
                        help=(
                            "Optional path relative to the configuration file's folder, "
                            "or an absolute path. It is retained for publisher "
                            "compatibility; the current built-in Markdown renderer does "
                            "not load custom templates."
                        ),
                    )
        return result

    def apply(self, form: dict[str, str]) -> None:
        for f in self.fields():
            key = f["id"]
            if key.startswith("editorial_policy.status.") and not form.get(
                "editorial_policy.statuses_present"
            ):
                continue
            if key not in form and f["kind"] != "checkbox":
                continue
            value: Any = form.get(key, "")
            if f["protected"] and not value:
                continue
            if f["kind"] != "checkbox" and value == (
                "" if f["value"] is None else str(f["value"])
            ):
                continue
            if f["kind"] == "checkbox":
                value = key in form
            elif f["kind"] == "lines":
                value = [line.strip() for line in value.splitlines() if line.strip()]
            if value == f["value"] or (value == "" and f["value"] is None):
                continue
            parts = key.split(".")
            if parts[0] == "publication":
                self.data["publication"][parts[1]] = value
                continue
            if parts[0] == "editorial_policy":
                policy = self.data.setdefault("editorial_policy", {})
                if parts[1] == "status":
                    statuses = list(
                        policy.get("statuses_eligible_for_issue", ["accepted"])
                    )
                    if value and parts[2] not in statuses:
                        statuses.append(parts[2])
                    elif not value and parts[2] in statuses:
                        statuses.remove(parts[2])
                    policy["statuses_eligible_for_issue"] = [
                        status for status in EDITORIAL_STATUSES if status in statuses
                    ]
                elif value == "":
                    policy.pop(parts[1], None)
                else:
                    policy[parts[1]] = value
                continue
            if parts[0] == "optimisation":
                optimisation = self.data.setdefault("optimisation", {})
                if parts[1] == "strategy":
                    optimisation["strategy"] = value
                else:
                    optimiser_settings = optimisation.setdefault("settings", {})
                    if value == "":
                        optimiser_settings.pop(parts[2], None)
                    else:
                        optimiser_settings[parts[2]] = value
                continue
            entry = self.data[parts[0]][int(parts[1])]
            if parts[2] in {"key", "name", "enabled"}:
                if value == "":
                    entry.pop(parts[2], None)
                else:
                    entry[parts[2]] = value
            elif parts[2] == "article":
                article = settings(entry)["articles"][int(parts[3])]
                if parts[4] == "authors":
                    value = [s.strip() for s in value.splitlines() if s.strip()]
                if value == "" and parts[4] != "title":
                    article.pop(parts[4], None)
                else:
                    article[parts[4]] = value
            elif parts[2] == "provider":
                existing = settings(entry)
                configured_provider = existing.get("provider")
                provider = (
                    copy.deepcopy(configured_provider)
                    if isinstance(configured_provider, dict)
                    else {
                        "type": configured_provider or "fake",
                        **{
                            k: existing[k]
                            for k in ("model", "response_text", "metadata")
                            if k in existing
                        },
                    }
                )
                if value == "":
                    provider.pop(parts[3], None)
                else:
                    provider[parts[3]] = value
                set_setting(entry, "provider", provider)
            elif parts[2] == "weight":
                weights = copy.deepcopy(settings(entry).get("weights") or {})
                if value == "":
                    weights.pop(parts[3], None)
                else:
                    weights[parts[3]] = value
                set_setting(entry, "weights", weights)
            else:
                set_setting(entry, parts[2], None if value == "" else value)
        self.revision += 1

    def validate(self) -> dict:
        data = copy.deepcopy(self.data)
        self.errors = {}
        if not str(data["publication"].get("name", "")).strip():
            self.errors["publication.name"] = "Enter a publication name."
        self._validate_policy_and_optimisation(data)
        for group in TYPES:
            identities = set()
            for i, entry in enumerate(data.get(group, [])):
                prefix = f"{group}.{i}"
                if entry["type"] not in TYPES[group]:
                    continue
                try:
                    ProcessorConfig.model_validate(entry)
                except ValueError:
                    self.errors[prefix + ".key"] = (
                        "Use letters, numbers, underscores or hyphens; start with a letter or number."
                    )
                identity = entry.get("key") or entry["type"]
                if group in {"extractors", "evaluators"} and entry.get("enabled", True):
                    if identity in identities:
                        self.errors[prefix + ".key"] = (
                            f"Give each enabled {group[:-1]} a unique key."
                        )
                    identities.add(identity)
                config = settings(entry)
                if entry["type"] == "rss" and config.get("url"):
                    try:
                        url = urlsplit(config["url"])
                        if url.scheme not in {"http", "https"} or not url.hostname:
                            raise ValueError
                    except ValueError:
                        self.errors[prefix + ".url"] = (
                            "Enter an HTTP or HTTPS feed URL."
                        )
                if entry["type"] == "rss" and not (
                    config.get("url") or config.get("path")
                ):
                    self.errors[prefix + ".url"] = (
                        "Enter a feed URL or local feed path."
                    )
                if entry["type"] == "static":
                    for j, article in enumerate(config.get("articles", [])):
                        try:
                            Article.model_validate(article)
                        except ValueError:
                            self.errors[f"{prefix}.article.{j}.title"] = (
                                "Check the article title, URL and published date."
                            )
                numbers = (
                    [(config, "words_per_minute", prefix, int)]
                    if entry["type"] == "reading_time"
                    else []
                )
                if entry["type"] == "llm_summary":
                    provider = config.get("provider", {"type": "fake"})
                    if provider.get("type") not in {"fake", "openai", "ollama"}:
                        self.errors[prefix + ".provider.type"] = (
                            "Choose a supported LLM provider."
                        )
                    if (
                        provider.get("type") != "fake"
                        and not str(provider.get("model", "")).strip()
                    ):
                        self.errors[prefix + ".provider.model"] = "Enter a model name."
                    numbers = [
                        (provider, key, prefix + ".provider", cast)
                        for key, cast in [("temperature", float), ("max_tokens", int)]
                    ]
                if entry["type"] == "rule_relevance":
                    numbers = [
                        (config.get("weights") or {}, key, prefix + ".weight", float)
                        for key in ("title", "summary", "content")
                    ]
                if entry["type"] in {"llm_relevance", "llm_summary_quality"}:
                    provider = config.get("provider", {"type": "fake"})
                    if not isinstance(provider, dict):
                        provider = {"type": provider}
                    if provider.get("type") not in {"fake", "openai", "ollama"}:
                        self.errors[prefix + ".provider.type"] = (
                            "Choose a supported LLM provider."
                        )
                    if (
                        provider.get("type") != "fake"
                        and not str(provider.get("model", "")).strip()
                    ):
                        self.errors[prefix + ".provider.model"] = "Enter a model name."
                    if (
                        entry["type"] == "llm_summary_quality"
                        and not str(
                            config.get("summary_extractor", "llm_summary")
                        ).strip()
                    ):
                        self.errors[prefix + ".summary_extractor"] = (
                            "Choose the summary extractor to evaluate."
                        )
                    numbers = [
                        (provider, key, prefix + ".provider", cast)
                        for key, cast in [("temperature", float), ("max_tokens", int)]
                    ]
                for obj, key, location, cast in numbers:
                    if key not in obj or obj[key] is None:
                        continue
                    try:
                        number = cast(obj[key])
                        if (
                            number < 0
                            or (
                                key in {"words_per_minute", "max_tokens"}
                                and number == 0
                            )
                            or str(number) in {"nan", "inf", "-inf"}
                        ):
                            raise ValueError
                        obj[key] = number
                        if entry["type"] == "reading_time":
                            set_setting(entry, key, number)
                        elif entry["type"] == "rule_relevance":
                            weights = copy.deepcopy(config.get("weights") or {})
                            weights[key] = number
                            set_setting(entry, "weights", weights)
                    except (ValueError, TypeError):
                        self.errors[f"{location}.{key}"] = (
                            "Enter a valid positive number."
                            if key != "temperature"
                            else "Enter a finite number of zero or greater."
                        )
        if self.errors:
            raise ValueError("Check the highlighted fields.")
        return data

    def _validate_policy_and_optimisation(self, data: dict) -> None:
        policy = data.get("editorial_policy") or {}
        for key in (
            "maximum_age_days",
            "maximum_articles",
            "maximum_reading_minutes",
        ):
            self._convert_number(
                policy,
                key,
                f"editorial_policy.{key}",
                int,
                minimum=1,
            )
        statuses = policy.get("statuses_eligible_for_issue", ["accepted"])
        if not statuses:
            self.errors["editorial_policy.status"] = (
                "Choose at least one eligible article status."
            )
        elif any(status not in EDITORIAL_STATUSES for status in statuses):
            self.errors["editorial_policy.status"] = (
                "Choose only supported article statuses."
            )

        optimisation = data.get("optimisation") or {}
        strategy = optimisation.get("strategy", "none")
        if strategy not in {"none", "greedy"}:
            self.errors["optimisation.strategy"] = (
                "Choose a supported optimisation strategy."
            )
        settings = optimisation.get("settings") or {}
        specifications = {
            "max_articles": (int, 1, None),
            "hard_minimum_relevance_score": (float, 0, 100),
            "relevance_target_score": (float, 0, 100),
            "relevance_target_weight": (float, 0, None),
            "reading_time_target_minutes": (float, 0, None),
            "reading_time_weight": (float, 0, None),
            "mandatory_terms_weight": (float, 0, None),
            "source_diversity_max_per_source": (int, 1, None),
            "source_diversity_weight": (float, 0, None),
        }
        for key, (cast, minimum, maximum) in specifications.items():
            self._convert_number(
                settings,
                key,
                f"optimisation.settings.{key}",
                cast,
                minimum=minimum,
                maximum=maximum,
            )
        mandatory_terms = settings.get("mandatory_terms", [])
        if not isinstance(mandatory_terms, list) or any(
            not isinstance(term, str) or not term.strip() for term in mandatory_terms
        ):
            self.errors["optimisation.settings.mandatory_terms"] = (
                "Enter one non-empty topic per line."
            )

    def _convert_number(
        self,
        obj: dict,
        key: str,
        location: str,
        cast,
        *,
        minimum: float,
        maximum: float | None = None,
    ) -> None:
        if key not in obj or obj[key] is None:
            return
        try:
            number = int(str(obj[key])) if cast is int else cast(obj[key])
            if (
                number < minimum
                or (maximum is not None and number > maximum)
                or str(number) in {"nan", "inf", "-inf"}
            ):
                raise ValueError
            obj[key] = number
        except (ValueError, TypeError):
            bounds = (
                f" between {minimum:g} and {maximum:g}"
                if maximum is not None
                else f" of {minimum:g} or greater"
            )
            self.errors[location] = f"Enter a valid number{bounds}."

    def save(self, destination: Path, overwrite: bool) -> None:
        data = self.validate()
        destination = destination.expanduser().absolute()
        if destination.suffix.lower() not in {".yaml", ".yml"}:
            raise ValueError("Use a .yaml or .yml filename.")
        if self.source and destination.parent.resolve() != self.source.parent:
            raise ValueError(
                "Save copies beside the original configuration to preserve relative resource paths."
            )
        if overwrite and (
            destination.resolve() != self.source
            or digest(self.source) != self.original_digest
        ):
            raise ValueError("The file changed on disk. Reopen it before saving.")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=destination.parent, suffix=".yaml", delete=False
            ) as stream:
                temporary = Path(stream.name)
                yaml.safe_dump(data, stream, sort_keys=False, allow_unicode=True)
            load_publication_config(temporary)
            if overwrite:
                os.chmod(temporary, self.source.stat().st_mode & 0o777)
                os.replace(temporary, destination)
            else:
                os.link(temporary, destination)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
        self.source = destination.resolve()
        self.original_digest = digest(self.source)
        self.data = data
        self.filename = destination.name

    def context(self) -> dict:
        fields = self.fields()
        return {
            "fields": fields,
            "groups": TYPES,
            "entries": {
                group: [
                    {
                        "type": entry["type"],
                        "index": i,
                        "fields": [
                            f for f in fields if f["id"].startswith(f"{group}.{i}.")
                        ],
                    }
                    for i, entry in enumerate(self.data.get(group, []))
                ]
                for group in TYPES
            },
            "draft": self,
        }
