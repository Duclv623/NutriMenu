export type Nutrients = {
  energy: number;
  carbs: number;
  protein: number;
  fat: number;
  fiber: number;
  sodium: number;
};
export type MealType = "breakfast" | "lunch" | "dinner" | "snack";
export type Ingredient = { id: string; name: string; grams: number };
export type Food = {
  id: string;
  name: string;
  category: string;
  description: string;
  emoji: string;
  color: string;
  image: string;
  minutes: number | null;
  grams: number;
  meals: MealType[];
  allergens: string[];
  ingredients: Ingredient[];
  nutrition: Nutrients;
  steps: string[];
  preparationGuideKind?: string;
  role?: string;
  giLevel?: string;
  listed?: boolean;
  servingRules?: { min: number; max: number; step: number };
  ingredientsComplete?: boolean;
  ingredientBasis?: "raw" | "cooked";
};
export type Profile = {
  name: string;
  age: number;
  dateOfBirth?: string;
  gender: string;
  height: number;
  weight: number;
  targetWeight: number;
  activity: string;
  goal: string;
  allergies: string[];
  excludedFoods: string[];
  preferences: string;
  pregnant: boolean;
  specialDiet: boolean;
  confirmed: boolean;
  version: number;
};
export type PlanItem = {
  id: string;
  foodId: string;
  meal: MealType;
  servings: number;
  locked: boolean;
  name?: string;
  // Snapshot for this item including servings; supplied by the optimizer.
  nutrition?: Nutrients;
};
export type SolverStatus =
  | "OPTIMAL"
  | "FEASIBLE"
  | "INFEASIBLE"
  | "UNKNOWN"
  | "MODEL_INVALID"
  | "NOT_RUN";
export type Plan = {
  id: string;
  date: string;
  profileVersion: number;
  version: number;
  items: PlanItem[];
  skippedItems?: PlanItem[];
  rating?: number | null;
  feedback?: string | null;
  solverStatus: SolverStatus;
  dataMode: "demo" | "api";
  target: number;
  notes: string[];
  createdAt: string;
  changeSignature?: string;
  validationPassed?: boolean;
};
export type GenerateInput = {
  date: string;
  target: number;
  snacks: boolean;
  maxMinutes: number;
  excludeRepeat: boolean;
};
export type User = { id: string; name: string; email: string; demo: boolean; role?: string };
export type Citation = {
  id: string;
  title: string;
  quote: string;
  source_url: string;
  document_url?: string;
  section?: string;
  pdf_pages?: number[];
};
export type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations?: Citation[];
  warnings?: string[];
  feedback?: string;
  remoteId?: string;
  historySaved?: boolean;
  mealResult?: MealResult;
};
export type Conversation = {
  id: string;
  title: string;
  messages: Message[];
  sessionId?: string;
  updatedAt: string;
  loaded?: boolean;
  planId?: string;
};
export type CheckIn = {
  id: string;
  date: string;
  weight: number;
  glucose?: number;
  note: string;
};
export type Workspace = {
  role?: string;
  profile: Profile;
  foods: Food[];
  plans: Plan[];
  favorites: string[];
  disliked?: string[];
  checkedShopping: string[];
  checkIns: CheckIn[];
  conversations: Conversation[];
  completedMeals: string[];
  capabilities?: {
    generate: boolean;
    swap: boolean;
    favoriteRemoval: boolean;
    cookingTime: boolean;
    atomicVersions: boolean;
    reason?: string;
  };
};

export type MealResult = {
  editor?: {
    planId: string;
    baseVersion: number;
    itemIds: string[];
    instruction: string;
    excludedTerms?: string[];
    preferredTerms?: string[];
    requestedServings?: number;
  };
  dataMode?: string;
  context?: {
    plan_id: string;
    plan_version?: number;
    item_id?: string;
    meal_type?: string;
  };
  choices?: { itemId: string; label: string; action: string }[];
  proposal?: {
    id: string;
    planId: string;
    baseVersion: number;
    expiresAt: number;
  } | null;
};
