export type LabSettings = {
  labUrl: string;
  cineforgeUrl: string;
  cineforgeProjectId?: string;
  quality: 'fast' | 'balanced' | 'quality';
  vision: boolean;
};

export type LabCapabilities = {
  panels?: boolean;
  ocr?: boolean;
  vision_llm?: boolean;
  vision_provider?: string;
  ready_for_pipeline?: boolean;
  notes?: string[];
};

export type HealthResponse = {
  ok: boolean;
  version: number;
  capabilities?: LabCapabilities;
};

const SETTINGS_KEY = 'lb:labSettings';

export function defaultLabUrl(): string {
  return import.meta.env.DEV ? '' : window.location.origin;
}

export function loadSettings(): LabSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return {
      labUrl: parsed.labUrl || defaultLabUrl(),
      cineforgeUrl: parsed.cineforgeUrl || 'http://127.0.0.1:8765',
      cineforgeProjectId: parsed.cineforgeProjectId,
      quality: parsed.quality || 'balanced',
      vision: Boolean(parsed.vision),
    };
  } catch {
    return {
      labUrl: defaultLabUrl(),
      cineforgeUrl: 'http://127.0.0.1:8765',
      quality: 'balanced',
      vision: false,
    };
  }
}

export function saveSettings(settings: LabSettings): void {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  localStorage.setItem('lb:labUrl', settings.labUrl);
}

export async function fetchHealth(base: string): Promise<HealthResponse> {
  const res = await fetch(`${base.replace(/\/$/, '')}/health`, {
    signal: AbortSignal.timeout(4000),
  });
  if (!res.ok) throw new Error('Lab health check failed');
  return res.json();
}

export async function importVault(
  base: string,
  manifest: unknown,
  projectId?: string | null,
): Promise<{ project_id: string; import?: { files_written?: number } }> {
  const res = await fetch(`${base}/api/import-vault`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ manifest, project_id: projectId }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Vault import failed');
  return data;
}

export async function runPipeline(
  base: string,
  file: File,
  opts: { projectId?: string | null; useVision: boolean },
): Promise<{ project_id: string; pipeline: Record<string, unknown> }> {
  const fd = new FormData();
  fd.append('image', file);
  if (opts.projectId) fd.append('project_id', opts.projectId);
  const qs = new URLSearchParams({
    use_vision: opts.useVision ? 'true' : 'false',
  });
  if (opts.projectId) qs.set('project_id', opts.projectId);
  const res = await fetch(`${base}/api/pipeline/run?${qs}`, { method: 'POST', body: fd });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Pipeline failed');
  return data;
}

export async function exportCineforge(
  base: string,
  body: {
    project_id: string;
    push: boolean;
    cineforge_url: string;
    cineforge_project_id?: string;
  },
): Promise<Record<string, unknown>> {
  const res = await fetch(`${base}/api/export-cineforge`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Export failed');
  return data;
}

export async function buildLivingPanels(
  base: string,
  projectId: string,
): Promise<{ living_panels_url?: string; choreography_lines?: number }> {
  const res = await fetch(`${base}/api/build-living-panels`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: projectId }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Living panels build failed');
  return data;
}