/**
 * Sentinel Learner 共享类型定义
 */

// 任务相关类型
export interface TaskInfo {
  taskId: string;
  taskName: string;
  domain: string;
  timestamp: number;
  path: string;
}

export interface TaskManifest {
  task_info: TaskInfo;
  events: TrainingEvent[];
  resources: ResourceMapping;
  summary: TaskSummary;
}

// Training Manifest 事件类型
export interface TrainingEvent {
  timestamp: number;
  video_time: string;
  task_id: string;
  sub_task_id: string | null;
  window_context: WindowContext;
  user_context: UserContext;
  event_details: EventDetails;
  file_io: FileIO | null;
  page_state: PageState;
  network_correlation: NetworkCorrelation;
  lineage: EventLineage;
  _metadata: EventMetadata;
}

export interface WindowContext {
  window_id: string;
  parent_window_id: string | null;
  url: string;
}

export interface UserContext {
  user_id: string | null;
  role: string | null;
  permissions: string[];
  env: Record<string, any> | null;
}

export interface EventDetails {
  action: string;
  semantic_label: string;
  dom_path: string | null;
  shadow_dom_path: string | null;
  coordinates: { x: number; y: number } | null;
}

export interface FileIO {
  type: string | null;
  local_path: string | null;
  content_summary: string | null;
}

export interface PageState {
  fingerprint: PageFingerprint | null;
  has_errors: boolean;
  is_loading: boolean;
  mutations: any[];
}

export interface PageFingerprint {
  hash: string;
  details: {
    path: string;
    query_keys: string[];
    title_normalized: string | null;
    dom_stats: DOMStats;
    page_type: string;
  };
}

export interface DOMStats {
  buttons: number;
  links: number;
  forms: number;
  inputs: number;
  images: number;
}

export interface NetworkCorrelation {
  api_requests: APIRequest[];
  static_resources?: StaticResource[];
  resources?: any[];
  response_status?: number | null;
}

export interface APIRequest {
  url: string;
  method: string;
  status: number;
  timestamp: number;
  resourceType: string;
  response?: {
    headers: Record<string, string[]>;
    body?: any;
  };
}

export interface StaticResource {
  filename: string;
  path: string;
  timestamp: number;
  size: number;
}

export interface EventLineage {
  previous_event_id: string | null;
  next_event_id: string | null;
}

export interface EventMetadata {
  event_id: string;
  title?: string;
  tagName?: string;
  text?: string;
  scrollX?: number;
  scrollY?: number;
  domSnapshotFileName?: string;
  domSnapshotPath?: string;
  user_intents?: string[];
  page_type?: string;
  [key: string]: any;
}

// 资源映射
export interface ResourceMapping {
  network: NetworkResources;
  dom: DOMSnapshots;
  video: VideoFiles;
}

export interface NetworkResources {
  api_traffic: string;
  resources: string[];
  response_bodies: string[];
}

export interface DOMSnapshots {
  full: string[];
  incremental: string[];
}

export interface VideoFiles {
  main: string | null;
  segments: string[];
}

// 任务摘要
export interface TaskSummary {
  total_events: number;
  unique_pages: number;
  unique_actions: string[];
  api_requests_count: number;
  static_resources_count: number;
  duration_ms: number;
}

// 学习结果
export interface LearningResult {
  task_id: string;
  knowledge: WebsiteKnowledge;
  operations: OperationPattern[];
  confidence: number;
}

export interface WebsiteKnowledge {
  domain: string;
  pages: PageKnowledge[];
  navigation_flow: NavigationFlow[];
  business_logic: BusinessLogic;
}

export interface PageKnowledge {
  url_pattern: string;
  page_type: string;
  fingerprint: string;
  structure: PageStructure;
  interactive_elements: InteractiveElement[];
  api_endpoints: string[];
}

export interface PageStructure {
  layout_type: string;
  components: string[];
  dom_stats: DOMStats;
}

export interface InteractiveElement {
  selector: string;
  tagName: string;
  text: string;
  action_type: string;
  intent: string[];
  frequency: number;
}

export interface NavigationFlow {
  from_page: string;
  to_page: string;
  trigger_action: string;
  frequency: number;
}

export interface BusinessLogic {
  user_flows: UserFlow[];
  data_patterns: DataPattern[];
  error_scenarios: ErrorScenario[];
}

export interface UserFlow {
  name: string;
  steps: FlowStep[];
  success_rate: number;
}

export interface FlowStep {
  action: string;
  target: string;
  expected_result: string;
}

export interface DataPattern {
  type: string;
  pattern: string;
  examples: string[];
}

export interface ErrorScenario {
  trigger: string;
  error_type: string;
  recovery_action: string;
}

export interface OperationPattern {
  pattern_id: string;
  action_sequence: string[];
  context: OperationContext;
  frequency: number;
  success_rate: number;
}

export interface OperationContext {
  page_type: string;
  user_intent: string[];
  required_elements: string[];
}

// 模拟操作
export interface SimulatedAction {
  action_id: string;
  type: string;
  target: TargetElement;
  timestamp: number;
  metadata: ActionMetadata;
}

export interface TargetElement {
  selector: string;
  tagName: string;
  text: string;
  coordinates?: { x: number; y: number };
}

export interface ActionMetadata {
  intent: string[];
  expected_outcome: string;
  confidence: number;
}

// 评估结果
export interface EvaluationResult {
  task_id: string;
  overall_similarity: number;
  metrics: MetricScores;
  comparison: ActionComparison[];
  report: EvaluationReport;
}

export interface MetricScores {
  action_sequence: number;
  dom_structure: number;
  network_request: number;
  timing: number;
}

export interface ActionComparison {
  original: TrainingEvent;
  simulated: SimulatedAction;
  similarity: number;
  differences: string[];
}

export interface EvaluationReport {
  summary: string;
  strengths: string[];
  weaknesses: string[];
  recommendations: string[];
}
