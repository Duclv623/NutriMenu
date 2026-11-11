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
  minutes: number;
  grams: number;
  meals: MealType[];
  allergens: string[];
  ingredients: Ingredient[];
  nutrition: Nutrients;
  steps: string[];
};
export type Profile = {
  name: string;
  age: number;
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
  solverStatus: SolverStatus;
  dataMode: "demo" | "api";
  target: number;
  notes: string[];
  createdAt: string;
};
export type GenerateInput = {
  date: string;
  target: number;
  snacks: boolean;
  maxMinutes: number;
  excludeRepeat: boolean;
};
export type User = { id: string; name: string; email: string; demo: boolean };
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
};
export type Conversation = {
  id: string;
  title: string;
  messages: Message[];
  sessionId?: string;
  updatedAt: string;
};
export type CheckIn = {
  id: string;
  date: string;
  weight: number;
  glucose?: number;
  note: string;
};
export type Workspace = {
  profile: Profile;
  foods: Food[];
  plans: Plan[];
  favorites: string[];
  checkedShopping: string[];
  checkIns: CheckIn[];
  conversations: Conversation[];
  completedMeals: string[];
};
