"""Boundary contract for TV1/TV2. No clinical defaults or target calculations."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

Amount = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Identifier = Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[\w:.-]+$")]
MealType = Literal["BREAKFAST", "LUNCH", "DINNER", "SNACK"]


class MealModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", alias_generator=to_camel, populate_by_name=True,
        serialize_by_alias=True, allow_inf_nan=False,
    )


class NutritionProfile(MealModel):
    profile_version: Annotated[int, Field(ge=1)]
    age: Annotated[int, Field(ge=1, le=120)] | None = None
    gender: Annotated[str, Field(max_length=50)] | None = None
    height: Annotated[float, Field(gt=0, le=300)] | None = None
    weight: Annotated[float, Field(gt=0, le=600)] | None = None
    activity_level: Annotated[str, Field(max_length=100)] | None = None
    goal: Annotated[str, Field(max_length=100)] | None = None
    target_weight: Annotated[float, Field(gt=0, le=600)] | None = None
    # null = not collected; [] = explicitly declared no known exclusions.
    allergies: list[Annotated[str, Field(min_length=1, max_length=100)]] | None = Field(default=None, max_length=100)
    restricted_ingredients: list[Annotated[str, Field(min_length=1, max_length=100)]] | None = Field(default=None, max_length=100)
    preferences: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(default_factory=list, max_length=100)
    # These are backend decisions, never inferred by the chatbot from demographics.
    scope_status: Literal["eligible", "out_of_scope", "unknown"] = "unknown"
    restrictions_resolved: bool = False
    excluded_ingredient_ids: list[Identifier] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def resolved_exclusions(self):
        if self.restrictions_resolved and (self.allergies or self.restricted_ingredients) and not self.excluded_ingredient_ids:
            raise ValueError("Declared exclusions require resolved ingredient IDs")
        return self


class Nutrients(MealModel):
    energy_kcal: Amount | None = None
    carbohydrate_g: Amount | None = None
    protein_g: Amount | None = None
    fat_g: Amount | None = None
    fiber_g: Amount | None = None
    sodium_mg: Amount | None = None


class NumericRange(MealModel):
    minimum: Amount | None = None
    maximum: Amount | None = None

    @model_validator(mode="after")
    def ordered(self):
        if self.minimum is None and self.maximum is None:
            raise ValueError("A bound is required")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("Minimum exceeds maximum")
        return self


class NutritionTarget(MealModel):
    version: Identifier
    source_refs: list[str] = Field(min_length=1, max_length=30)
    # Keys use the snake_case nutrient field names; values have explicit units in keys.
    bounds: dict[Literal["energy_kcal", "carbohydrate_g", "protein_g", "fat_g", "fiber_g", "sodium_mg"], NumericRange]
    # Ratios refer to actual plan energy, as specified in recom.docx.
    energy_percent: dict[Literal["carbohydrate_g", "protein_g", "fat_g"], NumericRange] = Field(default_factory=dict)

    @model_validator(mode="after")
    def explicit_target(self):
        if "energy_kcal" not in self.bounds:
            raise ValueError("Explicit energy bounds are required")
        if any(value.minimum is not None and value.minimum > 100 or value.maximum is not None and value.maximum > 100 for value in self.energy_percent.values()):
            raise ValueError("Energy shares must be percentages")
        return self


class Ingredient(MealModel):
    id: Identifier
    name: Annotated[str, Field(min_length=1, max_length=150)]


class PlanItem(MealModel):
    id: Identifier
    recipe_id: Identifier
    recipe_version: Identifier
    name: Annotated[str, Field(min_length=1, max_length=200)]
    meal_type: MealType
    portion_id: Identifier
    amount: Annotated[float, Field(gt=0)]
    unit: Literal["g", "ml", "serving"]
    state: Literal["raw", "cooked", "ready_to_eat", "unknown"]
    nutrition_basis: Literal["as_consumed", "raw_ingredients_estimate", "unknown"]
    nutrients: Nutrients
    ingredients: list[Ingredient] = Field(min_length=1, max_length=100)
    ingredients_complete: bool = False
    source_refs: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(min_length=1, max_length=30)


def sum_nutrients(items: list[PlanItem]) -> Nutrients:
    totals = {}
    for field in Nutrients.model_fields:
        values = [getattr(item.nutrients, field) for item in items]
        totals[field] = None if any(v is None for v in values) else float(sum((Decimal(str(v)) for v in values), Decimal(0)))
    return Nutrients(**totals)


class MealPlan(MealModel):
    id: Identifier
    version: Annotated[int, Field(ge=1)]
    profile_version: Annotated[int, Field(ge=1)]
    catalog_version: Identifier
    date: date
    solver_status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN", "MODEL_INVALID", "NOT_RUN"]
    validation_passed: bool
    checked_constraints: list[str] = Field(default_factory=list, max_length=100)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    target: NutritionTarget
    items: list[PlanItem] = Field(min_length=1, max_length=40)
    totals: Nutrients

    @model_validator(mode="after")
    def consistent_items(self):
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("Duplicate plan item IDs")
        actual = sum_nutrients(self.items)
        for field in Nutrients.model_fields:
            expected, claimed = getattr(actual, field), getattr(self.totals, field)
            if (expected is None) != (claimed is None) or expected is not None and abs(Decimal(str(expected)) - Decimal(str(claimed))) > Decimal("0.02"):
                raise ValueError(f"Plan total mismatch: {field}")
        return self


class MealSnapshot(MealModel):
    data_mode: Literal["mock", "http"]
    profile: NutritionProfile
    plan: MealPlan


class SwapRequest(MealModel):
    plan_id: Identifier
    base_version: Annotated[int, Field(ge=1)]
    item_id: Identifier
    instruction: Annotated[str, Field(min_length=1, max_length=2000)]


class SwapProposal(MealModel):
    id: UUID
    plan_id: Identifier
    base_version: Annotated[int, Field(ge=1)]
    profile_version: Annotated[int, Field(ge=1)]
    changed_item_id: Identifier
    expires_at: Annotated[float, Field(gt=0)]
    data_mode: Literal["mock", "http"]
    plan: MealPlan


class ApplySwap(MealModel):
    plan_id: Identifier
    proposal_id: UUID
    base_version: Annotated[int, Field(ge=1)]


class MealContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: Identifier | None = None
    plan_version: Annotated[int, Field(ge=1)] | None = None
    item_id: Identifier | None = None
    meal_type: MealType | None = None



class DemoProfileUpdate(MealModel):
    base_version: Annotated[int, Field(ge=1)]
    profile: NutritionProfile
