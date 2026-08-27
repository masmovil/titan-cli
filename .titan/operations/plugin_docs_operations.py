"""Operations for public plugin step documentation inventory."""

from __future__ import annotations

import importlib
import inspect
import json
import re
import sys
from pathlib import Path
from typing import Any


OFFICIAL_PLUGIN_REFS = {
    "git": {
        "package_dir": "plugins/titan-plugin-git",
        "plugin_ref": "titan_plugin_git.plugin:GitPlugin",
    },
    "github": {
        "package_dir": "plugins/titan-plugin-github",
        "plugin_ref": "titan_plugin_github.plugin:GitHubPlugin",
    },
    "jira": {
        "package_dir": "plugins/titan-plugin-jira",
        "plugin_ref": "titan_plugin_jira.plugin:JiraPlugin",
    },
    "slack": {
        "package_dir": "plugins/titan-plugin-slack",
        "plugin_ref": "titan_plugin_slack.plugin:SlackPlugin",
    },
}

WORKFLOW_STEPS_PAGE_PATHS = {
    "git": "docs/plugins/git/workflow-steps.md",
    "github": "docs/plugins/github/workflow-steps.md",
    "jira": "docs/plugins/jira/workflow-steps.md",
    "slack": "docs/plugins/slack/workflow-steps.md",
}

SECTION_HEADERS = [
    "Requires:",
    "Inputs (from ctx.data):",
    "Outputs (saved to ctx.data):",
    "Returns:",
]


def ensure_plugin_import_paths(repo_root: Path) -> None:
    """Add repo and official plugin packages to ``sys.path``."""
    candidate_paths = [repo_root] + [repo_root / ref["package_dir"] for ref in OFFICIAL_PLUGIN_REFS.values()]
    for path in reversed(candidate_paths):
        resolved = str(path)
        if resolved not in sys.path:
            sys.path.insert(0, resolved)


def load_grouping_metadata(repo_root: Path, plugin_name: str) -> dict[str, Any]:
    """Load the editorial grouping metadata for a plugin step reference page."""
    meta_path = repo_root / "docs" / "plugins" / "_meta" / f"{plugin_name}-step-groups.json"
    return json.loads(meta_path.read_text(encoding="utf-8"))


def load_public_plugin_steps(plugin_name: str) -> dict[str, Any]:
    """Load the public workflow steps exposed by an official plugin."""
    plugin_ref = OFFICIAL_PLUGIN_REFS[plugin_name]["plugin_ref"]
    module_name, class_name = plugin_ref.split(":", 1)
    module = importlib.import_module(module_name)
    plugin_cls = getattr(module, class_name)
    plugin = plugin_cls()
    return plugin.get_steps()


def extract_docstring_summary(docstring: str) -> str:
    """Return the first non-empty line from a docstring."""
    for line in inspect.cleandoc(docstring).splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def parse_docstring_sections(docstring: str) -> dict[str, list[str]]:
    """Parse the canonical public-step docstring sections."""
    cleaned = inspect.cleandoc(docstring)
    sections: dict[str, list[str]] = {header[:-1]: [] for header in SECTION_HEADERS}
    current_header: str | None = None

    for raw_line in cleaned.splitlines():
        line = raw_line.rstrip()
        if line in SECTION_HEADERS:
            current_header = line[:-1]
            continue
        if current_header and line:
            sections[current_header].append(line)

    return sections


def collect_plugin_workflow_usage(repo_root: Path, plugin_name: str) -> dict[str, list[str]]:
    """Map public step names to built-in workflow files that use them."""
    workflow_dir = repo_root / OFFICIAL_PLUGIN_REFS[plugin_name]["package_dir"] / f"titan_plugin_{plugin_name}" / "workflows"
    usage: dict[str, list[str]] = {}

    plugin_pattern = re.compile(r"^\s*plugin:\s*([A-Za-z0-9_\-]+)\s*$")
    step_pattern = re.compile(r"^\s*step:\s*([A-Za-z0-9_\-]+)\s*$")

    for workflow_path in sorted(workflow_dir.glob("*.yaml")):
        current_plugin: str | None = None
        for line in workflow_path.read_text(encoding="utf-8").splitlines():
            plugin_match = plugin_pattern.match(line)
            if plugin_match:
                current_plugin = plugin_match.group(1)
                continue

            step_match = step_pattern.match(line)
            if step_match:
                step_name = step_match.group(1)
                if current_plugin == plugin_name:
                    usage.setdefault(step_name, []).append(workflow_path.stem)
                current_plugin = None

    return {step_name: sorted(set(workflows)) for step_name, workflows in usage.items()}


def build_plugin_inventory(repo_root: Path, plugin_name: str) -> tuple[dict[str, Any], list[str]]:
    """Build structured inventory data and consistency errors for one plugin."""
    ensure_plugin_import_paths(repo_root)
    metadata = load_grouping_metadata(repo_root, plugin_name)
    public_steps = load_public_plugin_steps(plugin_name)
    workflow_usage = collect_plugin_workflow_usage(repo_root, plugin_name)

    grouped_steps: dict[str, str] = {}
    errors: list[str] = []
    for group in metadata["groups"]:
        for step in group["steps"]:
            step_name = step["name"]
            if step_name in grouped_steps:
                errors.append(f"step '{step_name}' appears in multiple groups")
            grouped_steps[step_name] = group["name"]

    for step_name in sorted(public_steps):
        if step_name not in grouped_steps:
            errors.append(f"public step '{step_name}' is missing from grouping metadata")

    for step_name in sorted(grouped_steps):
        if step_name not in public_steps:
            errors.append(f"grouping metadata references unknown public step '{step_name}'")

    steps_payload: list[dict[str, Any]] = []
    for step_name, step_fn in sorted(public_steps.items()):
        docstring = inspect.getdoc(step_fn) or ""
        sections = parse_docstring_sections(docstring)
        if not docstring:
            errors.append(f"public step '{step_name}' is missing a docstring")
        if not sections["Returns"]:
            errors.append(f"public step '{step_name}' is missing a Returns section")

        steps_payload.append(
            {
                "name": step_name,
                "group": grouped_steps.get(step_name),
                "module": step_fn.__module__,
                "function": step_fn.__name__,
                "summary": extract_docstring_summary(docstring),
                "docstring_sections": sections,
                "used_by_workflows": workflow_usage.get(step_name, []),
            }
        )

    return {
        "plugin": plugin_name,
        "groups": metadata["groups"],
        "steps": steps_payload,
    }, errors


def build_all_plugin_inventories(repo_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Build inventories and aggregate consistency errors for all official plugins."""
    inventories: list[dict[str, Any]] = []
    errors: list[str] = []

    for plugin_name in sorted(OFFICIAL_PLUGIN_REFS):
        inventory, plugin_errors = build_plugin_inventory(repo_root, plugin_name)
        inventories.append(inventory)
        errors.extend(f"{plugin_name}: {error}" for error in plugin_errors)

    return inventories, errors


def inventory_output_path(repo_root: Path, plugin_name: str) -> Path:
    """Return the generated JSON output path for a plugin inventory."""
    return repo_root / "docs" / "plugins" / "_generated" / f"{plugin_name}-step-inventory.json"


def step_reference_output_path(repo_root: Path, plugin_name: str) -> Path:
    """Return the generated Markdown output path for a plugin step reference."""
    return repo_root / "docs" / "plugins" / "generated" / f"{plugin_name}-step-reference.md"


def _clean_section_lines(lines: list[str]) -> list[str]:
    """Normalize docstring section lines for Markdown rendering."""
    cleaned: list[str] = []
    in_code_block = False

    for line in lines:
        normalized = line.strip()
        if not normalized:
            continue
        if normalized.startswith("- "):
            normalized = normalized[2:].strip()
        if normalized.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if normalized in {"Example:", "Examples:"}:
            break
        if normalized in {"Stores in:", "Output variables:", "Params:"}:
            continue
        if normalized.endswith(":") and ": " not in normalized:
            continue
        cleaned.append(normalized)
    return cleaned


def _parse_contract_line(line: str) -> tuple[str, str, str]:
    """Parse a docstring contract line into name, type, and description columns."""
    match = re.match(r"^(?P<name>[^:(]+?)\s*(?:\((?P<type>[^)]+)\))?:\s*(?P<desc>.+)$", line)
    if not match:
        return line, "", ""

    name = match.group("name").strip()
    item_type = (match.group("type") or "").strip()
    description = match.group("desc").strip()
    return name, item_type, description


def _parse_return_line(line: str) -> tuple[str, str]:
    """Parse a Returns line into result type and description."""
    match = re.match(r"^(?P<result>[A-Za-z_][A-Za-z0-9_ ]*):\s*(?P<desc>.+)$", line)
    if not match:
        return line, ""

    return match.group("result").strip(), match.group("desc").strip()


def _append_contract_table(lines: list[str], title: str, section_lines: list[str]) -> None:
    """Append a structured Markdown table for contract sections."""
    if not section_lines:
        return

    lines.append(f"**{title}**")
    lines.append("")

    if title == "Returns":
        lines.append("| Result | Saved for later steps | Description |")
        lines.append("|--------|-----------------------|-------------|")
        for line in section_lines:
            result, description = _parse_return_line(line)
            if not description:
                description = "-"
            lines.append(f"| `{result}` | - | {description} |")
        lines.append("")
        return

    lines.append("| Name | Type | Description |")
    lines.append("|------|------|-------------|")
    for line in section_lines:
        name, item_type, description = _parse_contract_line(line)
        display_name = f"`{name}`" if description else name
        lines.append(f"| {display_name} | {item_type or '-'} | {description or '-'} |")
    lines.append("")


def _extract_output_names(section_lines: list[str]) -> list[str]:
    """Extract output names from an Outputs section."""
    names: list[str] = []
    for line in section_lines:
        name, _, _ = _parse_contract_line(line)
        if name:
            names.append(name)
    return names


def _append_returns_table_with_outputs(lines: list[str], section_lines: list[str], output_names: list[str]) -> None:
    """Append a Returns table that also highlights what later steps can read."""
    lines.append("**Returns**")
    lines.append("")
    lines.append("| Result | Saved for later steps | Description |")
    lines.append("|--------|-----------------------|-------------|")

    for line in section_lines:
        result, description = _parse_return_line(line)
        saved = "-"
        if result in {"Success", "Skip"} and output_names:
            saved = ", ".join(f"`{name}`" for name in output_names)
        lines.append(f"| `{result}` | {saved} | {description or '-'} |")

    lines.append("")


def render_plugin_step_reference_markdown(inventory: dict[str, Any]) -> str:
    """Render a detailed Markdown step reference page for one plugin."""
    plugin_name = inventory["plugin"]
    steps_by_name = {step["name"]: step for step in inventory["steps"]}

    lines = [
        f"# {plugin_name.capitalize()} Step Reference",
        "",
        "This page is generated from the public step inventory and shows the documented workflow contract for each public step.",
        "",
    ]

    for group in inventory["groups"]:
        lines.append(f"## {group['name']}")
        lines.append("")

        for grouped_step in group["steps"]:
            step = steps_by_name[grouped_step["name"]]
            sections = step["docstring_sections"]

            lines.append(f"### `{step['name']}`")
            lines.append("")
            lines.append(step["summary"] or grouped_step.get("summary", ""))
            lines.append("")

            lines.append("**How to read this contract**")
            lines.append("")
            lines.append("- `Inputs (from ctx.data)` shows what the step expects before it runs.")
            lines.append("- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.")
            lines.append("- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.")
            lines.append("")

            lines.append("**Workflow usage**")
            lines.append("")
            lines.append("```yaml")
            lines.append(f"- plugin: {plugin_name}")
            lines.append(f"  step: {step['name']}")
            lines.append("```")
            lines.append("")

            if step["used_by_workflows"]:
                joined = ", ".join(f"`{name}`" for name in step["used_by_workflows"])
                lines.append(f"**Used by built-in workflows:** {joined}")
                lines.append("")

            output_names = _extract_output_names(
                _clean_section_lines(sections.get("Outputs (saved to ctx.data)", []))
            )
            if output_names:
                joined = ", ".join(f"`{name}`" for name in output_names)
                lines.append(f"**Available to later steps:** {joined}")
                lines.append("")

            for title in ["Requires", "Inputs (from ctx.data)", "Outputs (saved to ctx.data)", "Returns"]:
                section_lines = _clean_section_lines(sections.get(title, []))
                if not section_lines:
                    continue
                if title == "Returns":
                    _append_returns_table_with_outputs(lines, section_lines, output_names)
                else:
                    _append_contract_table(lines, title, section_lines)

    return "\n".join(lines).rstrip() + "\n"


def render_plugin_inline_step_contracts_markdown(inventory: dict[str, Any]) -> str:
    """Render detailed step contracts to embed inside a plugin workflow-steps page."""
    plugin_name = inventory["plugin"]
    steps_by_name = {step["name"]: step for step in inventory["steps"]}

    lines = [
        "## Detailed Step Contracts",
        "",
        f"The summaries above show what each {plugin_name} step is for. The sections below show the documented contract for each public step: what it expects from `ctx.data`, what it saves back, and what result types it may return.",
        "",
        "Expand a step to see its workflow usage, required context, inputs, outputs, and result behavior.",
        "",
        "How to read these contracts:",
        "",
        "- `Inputs (from ctx.data)` = values the step expects before it runs.",
        "- `Outputs (saved to ctx.data)` = metadata keys saved for later steps when the step returns `Success` or `Skip`.",
        "- `Returns` = the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate payload.",
        "",
    ]

    for group in inventory["groups"]:
        lines.append(f"### {group['name']}")
        lines.append("")

        for grouped_step in group["steps"]:
            step = steps_by_name[grouped_step["name"]]
            sections = step["docstring_sections"]

            lines.append(f'??? info "`{step["name"]}`"')
            lines.append(f'    {step["summary"] or grouped_step.get("summary", "")}' )
            lines.append("")
            lines.append("    **Workflow usage**")
            lines.append("")
            lines.append("    ```yaml")
            lines.append(f"    - plugin: {plugin_name}")
            lines.append(f"      step: {step['name']}")
            lines.append("    ```")
            lines.append("")

            if step["used_by_workflows"]:
                joined = ", ".join(f"`{name}`" for name in step["used_by_workflows"])
                lines.append(f"    **Used by built-in workflows:** {joined}")
                lines.append("")

            output_names = _extract_output_names(
                _clean_section_lines(sections.get("Outputs (saved to ctx.data)", []))
            )
            if output_names:
                joined = ", ".join(f"`{name}`" for name in output_names)
                lines.append(f"    **Available to later steps:** {joined}")
                lines.append("")

            for title in ["Requires", "Inputs (from ctx.data)", "Outputs (saved to ctx.data)", "Returns"]:
                section_lines = _clean_section_lines(sections.get(title, []))
                if not section_lines:
                    if title in {"Inputs (from ctx.data)", "Outputs (saved to ctx.data)"}:
                        lines.append(f"    **{title}**")
                        lines.append("")
                        lines.append("    None documented.")
                        lines.append("")
                    continue

                table_lines: list[str] = []
                if title == "Returns":
                    _append_returns_table_with_outputs(table_lines, section_lines, output_names)
                else:
                    _append_contract_table(table_lines, title, section_lines)
                for table_line in table_lines:
                    if table_line:
                        lines.append(f"    {table_line}")
                    else:
                        lines.append("")

            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def workflow_steps_page_path(repo_root: Path, plugin_name: str) -> Path:
    """Return the workflow-steps page path for a plugin."""
    return repo_root / WORKFLOW_STEPS_PAGE_PATHS[plugin_name]


def update_plugin_workflow_steps_pages(repo_root: Path, inventories: list[dict[str, Any]]) -> list[Path]:
    """Inject generated detailed step contracts into plugin workflow-steps pages."""
    start_marker = "<!-- BEGIN GENERATED STEP CONTRACTS -->"
    end_marker = "<!-- END GENERATED STEP CONTRACTS -->"
    updated_paths: list[Path] = []

    for inventory in inventories:
        page_path = workflow_steps_page_path(repo_root, inventory["plugin"])
        content = page_path.read_text(encoding="utf-8")
        generated = render_plugin_inline_step_contracts_markdown(inventory)
        replacement = f"{start_marker}\n{generated}{end_marker}"

        if start_marker not in content or end_marker not in content:
            raise ValueError(f"Missing step contract markers in {page_path}")

        pattern = re.compile(
            re.escape(start_marker) + r".*?" + re.escape(end_marker),
            re.DOTALL,
        )
        updated = pattern.sub(replacement, content)
        page_path.write_text(updated, encoding="utf-8")
        updated_paths.append(page_path)

    return updated_paths


def write_plugin_inventories(repo_root: Path, inventories: list[dict[str, Any]]) -> list[Path]:
    """Write generated inventory JSON files to the docs tree."""
    output_dir = repo_root / "docs" / "plugins" / "_generated"
    output_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    for inventory in inventories:
        output_path = inventory_output_path(repo_root, inventory["plugin"])
        output_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
        paths.append(output_path)
    return paths


def write_plugin_step_references(repo_root: Path, inventories: list[dict[str, Any]]) -> list[Path]:
    """Write generated Markdown step reference pages to the docs tree."""
    output_dir = repo_root / "docs" / "plugins" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    for inventory in inventories:
        output_path = step_reference_output_path(repo_root, inventory["plugin"])
        output_path.write_text(render_plugin_step_reference_markdown(inventory), encoding="utf-8")
        paths.append(output_path)
    return paths


def validate_generated_inventories(repo_root: Path, inventories: list[dict[str, Any]]) -> list[str]:
    """Validate that generated inventory files exist and match current computed output."""
    errors: list[str] = []

    for inventory in inventories:
        expected = json.dumps(inventory, indent=2) + "\n"
        output_path = inventory_output_path(repo_root, inventory["plugin"])
        if not output_path.exists():
            errors.append(f"missing generated inventory: {output_path.relative_to(repo_root)}")
            continue

        current = output_path.read_text(encoding="utf-8")
        if current != expected:
            errors.append(f"stale generated inventory: {output_path.relative_to(repo_root)}")

    return errors


def validate_generated_step_references(repo_root: Path, inventories: list[dict[str, Any]]) -> list[str]:
    """Validate that generated Markdown step references exist and are up to date."""
    errors: list[str] = []

    for inventory in inventories:
        expected = render_plugin_step_reference_markdown(inventory)
        output_path = step_reference_output_path(repo_root, inventory["plugin"])
        if not output_path.exists():
            errors.append(f"missing generated step reference: {output_path.relative_to(repo_root)}")
            continue

        current = output_path.read_text(encoding="utf-8")
        if current != expected:
            errors.append(f"stale generated step reference: {output_path.relative_to(repo_root)}")

    return errors


def validate_workflow_steps_pages(repo_root: Path, inventories: list[dict[str, Any]]) -> list[str]:
    """Validate that inline generated contracts inside workflow-steps pages are up to date."""
    errors: list[str] = []
    start_marker = "<!-- BEGIN GENERATED STEP CONTRACTS -->"
    end_marker = "<!-- END GENERATED STEP CONTRACTS -->"

    for inventory in inventories:
        page_path = workflow_steps_page_path(repo_root, inventory["plugin"])
        content = page_path.read_text(encoding="utf-8")
        generated = render_plugin_inline_step_contracts_markdown(inventory)
        expected_block = f"{start_marker}\n{generated}{end_marker}"

        if start_marker not in content or end_marker not in content:
            errors.append(f"missing generated contract markers: {page_path.relative_to(repo_root)}")
            continue

        pattern = re.compile(
            re.escape(start_marker) + r".*?" + re.escape(end_marker),
            re.DOTALL,
        )
        match = pattern.search(content)
        if not match:
            errors.append(f"unable to read generated contract block: {page_path.relative_to(repo_root)}")
            continue

        if match.group(0) != expected_block:
            errors.append(f"stale generated contract block: {page_path.relative_to(repo_root)}")

    return errors


__all__ = [
    "OFFICIAL_PLUGIN_REFS",
    "build_all_plugin_inventories",
    "build_plugin_inventory",
    "extract_docstring_summary",
    "inventory_output_path",
    "parse_docstring_sections",
    "render_plugin_inline_step_contracts_markdown",
    "render_plugin_step_reference_markdown",
    "step_reference_output_path",
    "update_plugin_workflow_steps_pages",
    "validate_generated_inventories",
    "validate_generated_step_references",
    "validate_workflow_steps_pages",
    "write_plugin_inventories",
    "write_plugin_step_references",
    "workflow_steps_page_path",
]
