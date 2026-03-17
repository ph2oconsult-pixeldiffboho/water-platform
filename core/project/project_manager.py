"""
core/project/project_manager.py

Handles all project lifecycle operations: create, save, load, clone,
delete, and list.  Storage backend is currently local JSON files;
the interface is designed for future migration to cloud storage.
"""

from __future__ import annotations
import json
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import uuid

from core.project.project_model import (
    DomainType, ProjectMetadata, ProjectModel, ScenarioModel, ScenarioType,
    TreatmentPathway, AssumptionsSet,
)


DEFAULT_STORAGE_PATH = Path("storage/projects")


class ProjectManager:
    """
    Manages the full lifecycle of projects.

    All projects are stored as JSON files.  Each project is one file named
    by its project_id.  The storage path is configurable at construction.
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or DEFAULT_STORAGE_PATH
        self.storage_path.mkdir(parents=True, exist_ok=True)

    # ── CREATE ────────────────────────────────────────────────────────────

    def create_project(
        self,
        project_name: str,
        domain: DomainType,
        plant_name: str = "",
        plant_location: str = "",
        author: str = "",
        client_name: str = "",
        project_number: str = "",
        notes: str = "",
    ) -> ProjectModel:
        """
        Create a new empty project with metadata.
        A default Base Case scenario is added automatically.
        """
        metadata = ProjectMetadata(
            project_name=project_name,
            domain=domain,
            plant_name=plant_name,
            plant_location=plant_location,
            author=author,
            client_name=client_name,
            project_number=project_number,
            notes=notes,
        )
        project = ProjectModel(metadata=metadata)

        # Create a default Base Case scenario
        base_scenario = ScenarioModel(
            scenario_name="Base Case",
            scenario_type=ScenarioType.BASE_CASE,
            description="Initial base case scenario",
        )
        project.add_scenario(base_scenario)
        project.log_change("Project created", author=author)

        return project

    # ── SAVE ──────────────────────────────────────────────────────────────

    def save(self, project: ProjectModel) -> Path:
        """
        Serialise and save a project to JSON.
        Returns the path of the saved file.
        """
        project.metadata.last_modified = datetime.now(timezone.utc).isoformat()
        file_path = self._project_path(project.metadata.project_id)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(project.to_dict(), f, indent=2, default=str)
        return file_path

    # ── LOAD ──────────────────────────────────────────────────────────────

    def load(self, project_id: str) -> ProjectModel:
        """Load a project from storage by its ID."""
        file_path = self._project_path(project_id)
        if not file_path.exists():
            raise FileNotFoundError(
                f"Project '{project_id}' not found at {file_path}"
            )
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ProjectModel.from_dict(data)

    # ── LIST ──────────────────────────────────────────────────────────────

    def list_projects(self) -> List[Dict]:
        """
        Return a summary list of all saved projects.
        Reads only the metadata section — does not load full project objects.
        """
        projects = []
        for file_path in sorted(self.storage_path.glob("*.json")):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                meta = data.get("metadata", {})
                scenario_count = len(data.get("scenarios", {}))
                projects.append({
                    "project_id": meta.get("project_id", ""),
                    "project_name": meta.get("project_name", "Unnamed"),
                    "domain": meta.get("domain", ""),
                    "plant_name": meta.get("plant_name", ""),
                    "client_name": meta.get("client_name", ""),
                    "author": meta.get("author", ""),
                    "last_modified": meta.get("last_modified", ""),
                    "scenario_count": scenario_count,
                    "file_path": str(file_path),
                })
            except Exception:
                pass  # Skip corrupt files
        return projects

    # ── DELETE ────────────────────────────────────────────────────────────

    def delete(self, project_id: str) -> None:
        """Permanently delete a project file."""
        file_path = self._project_path(project_id)
        if file_path.exists():
            file_path.unlink()

    # ── Internal helpers ──────────────────────────────────────────────────

    def _project_path(self, project_id: str) -> Path:
        """Return the full file path for a project JSON file."""
        return self.storage_path / f"{project_id}.json"

    # ── CLONE PROJECT ─────────────────────────────────────────────────────

    def clone_project(
        self,
        source_project: ProjectModel,
        new_name: str,
        author: str = "",
    ) -> ProjectModel:
        """
        Create a deep copy of a project with a new ID and name.
        All scenarios are cloned and given new IDs.
        """
        cloned = deepcopy(source_project)
        cloned.metadata.project_id = str(uuid.uuid4())
        cloned.metadata.project_name = new_name
        cloned.metadata.author = author or cloned.metadata.author
        cloned.metadata.created_at = datetime.now(timezone.utc).isoformat()
        cloned.metadata.last_modified = datetime.now(timezone.utc).isoformat()
        cloned.metadata.version = "1.0.0"
        cloned.version_history = []

        # Re-ID all scenarios
        new_scenarios = {}
        new_active_id = None
        for old_id, scenario in cloned.scenarios.items():
            new_id = str(uuid.uuid4())
            scenario.scenario_id = new_id
            scenario.created_at = datetime.now(timezone.utc).isoformat()
            scenario.is_stale = True
            new_scenarios[new_id] = scenario
            if old_id == source_project.active_scenario_id:
                new_active_id = new_id

        cloned.scenarios = new_scenarios
        cloned.active_scenario_id = new_active_id
        cloned.log_change(
            f"Cloned from '{source_project.metadata.project_name}'",
            author=author,
        )
        return cloned


class ScenarioManager:
    """
    Manages scenario lifecycle within a project.
    Operates directly on ProjectModel objects.
    """

    def add_scenario(
        self,
        project: ProjectModel,
        scenario_name: str,
        scenario_type: ScenarioType = ScenarioType.OPTION_A,
        description: str = "",
        copy_from_id: Optional[str] = None,
    ) -> ScenarioModel:
        """
        Add a new scenario to a project.
        Optionally clones inputs and pathway from an existing scenario.
        """
        if copy_from_id and copy_from_id in project.scenarios:
            source = project.scenarios[copy_from_id]
            new_scenario = deepcopy(source)
            new_scenario.scenario_id = str(uuid.uuid4())
            new_scenario.cost_result = None
            new_scenario.carbon_result = None
            new_scenario.risk_result = None
            new_scenario.validation_result = None
            new_scenario.domain_specific_outputs = {}
            new_scenario.is_stale = True
            new_scenario.last_calculated_at = None
        else:
            new_scenario = ScenarioModel()

        new_scenario.scenario_name = scenario_name
        new_scenario.scenario_type = scenario_type
        new_scenario.description = description
        new_scenario.created_at = datetime.now(timezone.utc).isoformat()
        new_scenario.last_modified = datetime.now(timezone.utc).isoformat()

        project.add_scenario(new_scenario)
        project.log_change(f"Scenario '{scenario_name}' added")
        return new_scenario

    def clone_scenario(
        self,
        project: ProjectModel,
        source_scenario_id: str,
        new_name: str,
    ) -> ScenarioModel:
        """Clone a scenario within the same project."""
        return self.add_scenario(
            project,
            scenario_name=new_name,
            copy_from_id=source_scenario_id,
        )

    def set_preferred(
        self, project: ProjectModel, scenario_id: str
    ) -> None:
        """Mark one scenario as the preferred option."""
        for scenario in project.scenarios.values():
            scenario.is_preferred = (scenario.scenario_id == scenario_id)

    def delete_scenario(
        self, project: ProjectModel, scenario_id: str
    ) -> None:
        """Remove a scenario from the project."""
        if len(project.scenarios) <= 1:
            raise ValueError("Cannot delete the last remaining scenario.")
        scenario_name = project.scenarios.get(scenario_id, ScenarioModel()).scenario_name
        project.remove_scenario(scenario_id)
        project.log_change(f"Scenario '{scenario_name}' deleted")

    def compare_scenarios(
        self,
        project: ProjectModel,
        scenario_ids: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Return a flat comparison summary of scenarios.
        Used to populate comparison tables in the UI and reports.
        """
        ids = scenario_ids or list(project.scenarios.keys())
        comparison = []

        for sid in ids:
            scenario = project.scenarios.get(sid)
            if not scenario:
                continue

            row: Dict = {
                "scenario_id": scenario.scenario_id,
                "scenario_name": scenario.scenario_name,
                "scenario_type": scenario.scenario_type.display_name,
                "is_preferred": scenario.is_preferred,
                "design_flow_mld": scenario.design_flow_mld,
                "technologies": (
                    ", ".join(scenario.treatment_pathway.technology_sequence)
                    if scenario.treatment_pathway else "Not selected"
                ),
                "is_stale": scenario.is_stale,
            }

            if scenario.cost_result:
                row["capex_total_m"] = round(scenario.cost_result.capex_total / 1e6, 2)
                row["opex_annual_k"] = round(scenario.cost_result.opex_annual / 1e3, 1)
                row["lifecycle_cost_annual_k"] = round(
                    scenario.cost_result.lifecycle_cost_annual / 1e3, 1
                )
                row["specific_cost_per_kl"] = scenario.cost_result.specific_cost_per_kl

            if scenario.carbon_result:
                row["net_tco2e_yr"] = round(scenario.carbon_result.net_tco2e_yr, 1)
                row["specific_kg_co2e_per_kl"] = scenario.carbon_result.specific_kg_co2e_per_kl

            if scenario.risk_result:
                row["overall_risk_score"] = round(scenario.risk_result.overall_score, 1)
                row["overall_risk_level"] = scenario.risk_result.overall_level

            comparison.append(row)

        return comparison
