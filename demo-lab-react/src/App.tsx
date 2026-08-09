import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Drawer,
  Form,
  Input,
  Layout,
  Modal,
  Row,
  Space,
  Steps,
  Switch,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd';
import {
  CloudUploadOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import type { UploadProps } from 'antd';
import {
  buildLivingPanels,
  exportCineforge,
  fetchHealth,
  importVault,
  loadSettings,
  runPipeline,
  saveSettings,
  type LabCapabilities,
  type LabSettings,
} from './api/lab';
import { PORTFOLIO } from './theme/portfolio';

const { Header, Content } = Layout;
const { Title, Paragraph, Text } = Typography;

const PIPELINE_STEPS = [
  'Analyze',
  'Panels',
  'OCR',
  'Interpret',
  'Choreo',
  'Living',
  'Export',
];

export default function App() {
  const [settings, setSettings] = useState<LabSettings>(() => loadSettings());
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [form] = Form.useForm<LabSettings>();
  const [labOnline, setLabOnline] = useState(false);
  const [labVersion, setLabVersion] = useState<number | null>(null);
  const [capabilities, setCapabilities] = useState<LabCapabilities | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [currentFile, setCurrentFile] = useState<File | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [running, setRunning] = useState(false);
  const [panelCount, setPanelCount] = useState<number | null>(null);

  const apiBase = settings.labUrl.replace(/\/$/, '');

  const refreshHealth = useCallback(async () => {
    try {
      const h = await fetchHealth(apiBase);
      setLabOnline(Boolean(h.ok));
      setLabVersion(h.version ?? null);
      setCapabilities(h.capabilities ?? null);
    } catch {
      setLabOnline(false);
      setLabVersion(null);
      setCapabilities(null);
    }
  }, [apiBase]);

  useEffect(() => {
    refreshHealth();
    const id = window.setInterval(refreshHealth, 15000);
    return () => window.clearInterval(id);
  }, [refreshHealth]);

  const openSettings = () => {
    form.setFieldsValue(settings);
    setSettingsOpen(true);
  };

  const saveSettingsForm = async () => {
    const values = await form.validateFields();
    setSettings(values);
    saveSettings(values);
    setSettingsOpen(false);
    message.success('Settings saved');
    refreshHealth();
  };

  const handleVaultUpload: UploadProps['beforeUpload'] = async (file) => {
    try {
      const text = await file.text();
      const manifest = JSON.parse(text);
      const data = await importVault(apiBase, manifest, projectId);
      setProjectId(data.project_id);
      message.success(`Vault imported · ${data.import?.files_written ?? 0} file(s)`);
    } catch (e) {
      message.error(e instanceof Error ? e.message : 'Invalid manifest');
    }
    return false;
  };

  const handleImageUpload: UploadProps['beforeUpload'] = (file) => {
    setCurrentFile(file);
    setStepIndex(0);
    return false;
  };

  const handleRunPipeline = async () => {
    if (!currentFile) {
      message.warning('Upload a comic page image first');
      return;
    }
    if (!labOnline) {
      message.error('Start lab_server.py on :8042');
      return;
    }
    setRunning(true);
    setStepIndex(0);
    try {
      for (let i = 0; i < PIPELINE_STEPS.length - 1; i += 1) {
        setStepIndex(i);
        await new Promise((r) => setTimeout(r, 120));
      }
      const data = await runPipeline(apiBase, currentFile, {
        projectId,
        useVision: settings.vision,
      });
      setProjectId(data.project_id);
      const interp = (data.pipeline?.interpretation ?? {}) as Record<string, unknown>;
      const scenes = (interp.scenes ?? []) as unknown[];
      const panels = Number((data.pipeline as Record<string, unknown>)?.panel_count ?? scenes.length);
      setPanelCount(Number.isFinite(panels) ? panels : null);
      setStepIndex(PIPELINE_STEPS.length - 1);
      message.success(`Pipeline complete · project ${data.project_id}`);
    } catch (e) {
      message.error(e instanceof Error ? e.message : 'Pipeline failed');
    } finally {
      setRunning(false);
    }
  };

  const handleExportCineforge = () => {
    if (!projectId) {
      message.warning('Run the pipeline first');
      return;
    }
    let cfProjectId = settings.cineforgeProjectId ?? '';
    Modal.confirm({
      title: 'Push to CineForge?',
      content: 'OK = push to running backend. Cancel = export file only.',
      okText: 'Push',
      cancelText: 'Export only',
      onOk: () =>
        new Promise<void>((resolve, reject) => {
          Modal.confirm({
            title: 'CineForge project ID',
            content: (
              <Input
                defaultValue={cfProjectId}
                placeholder="Create project in cineforge first"
                onChange={(e) => {
                  cfProjectId = e.target.value.trim();
                }}
              />
            ),
            onOk: async () => {
              if (!cfProjectId) {
                message.warning('Project ID required');
                reject(new Error('missing project id'));
                return;
              }
              const next = { ...settings, cineforgeProjectId: cfProjectId };
              setSettings(next);
              saveSettings(next);
              try {
                const data = await exportCineforge(apiBase, {
                  project_id: projectId,
                  push: true,
                  cineforge_url: settings.cineforgeUrl,
                  cineforge_project_id: cfProjectId,
                });
                message.success(`Ingested ${data.shot_count} shot(s)`);
                if (data.cineforge_ui_url) window.open(String(data.cineforge_ui_url), '_blank');
                resolve();
              } catch (e) {
                message.error(e instanceof Error ? e.message : 'Push failed');
                reject(e);
              }
            },
          });
        }),
      onCancel: async () => {
        try {
          const data = await exportCineforge(apiBase, {
            project_id: projectId,
            push: false,
            cineforge_url: settings.cineforgeUrl,
          });
          message.success(`Export ready · ${data.shot_count} shot(s)`);
        } catch (e) {
          message.error(e instanceof Error ? e.message : 'Export failed');
        }
      },
    });
  };

  const handleLivingPanels = async () => {
    if (!projectId) return;
    try {
      const data = await buildLivingPanels(apiBase, projectId);
      message.success(`Living panels · ${data.choreography_lines ?? 0} line(s)`);
      if (data.living_panels_url) {
        window.open(`${apiBase}${data.living_panels_url}`, '_blank');
      }
    } catch (e) {
      message.error(e instanceof Error ? e.message : 'Build failed');
    }
  };

  const reset = () => {
    setCurrentFile(null);
    setStepIndex(0);
    setPanelCount(null);
    setProjectId(null);
  };

  const statusColor = labOnline ? 'success' : 'error';
  const statusText = labOnline
    ? `Lab online v${labVersion ?? '?'}${capabilities?.ready_for_pipeline ? '' : ' · pipeline deps missing'}`
    : 'Lab offline — run python -m lookbook.lab_server';

  return (
    <Layout style={{ minHeight: '100vh', background: PORTFOLIO.bg }}>
      <Header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: `1px solid ${PORTFOLIO.border}`,
          padding: '0 24px',
        }}
      >
        <div>
          <Title level={4} style={{ margin: 0, color: PORTFOLIO.text }}>
            lookBOOK <span style={{ color: PORTFOLIO.accent }}>Demo Lab</span>
          </Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            Ant Design shell · same lab_server API
          </Text>
        </div>
        <Space>
          <Button icon={<SettingOutlined />} onClick={openSettings}>
            Settings
          </Button>
          <Button type="link" href="/" style={{ color: PORTFOLIO.muted }}>
            Legacy v2
          </Button>
        </Space>
      </Header>

      <Content style={{ padding: 24, maxWidth: 1100, margin: '0 auto', width: '100%' }}>
        <Alert
          type={statusColor}
          showIcon
          message={statusText}
          style={{ marginBottom: 16 }}
        />

        <Row gutter={[16, 16]}>
          <Col xs={24} md={12}>
            <Card title="Source" bordered={false}>
              <Upload.Dragger
                accept="image/*,.cbz,.cbr,.zip,.rar"
                maxCount={1}
                beforeUpload={handleImageUpload}
                onRemove={() => setCurrentFile(null)}
              >
                <p className="ant-upload-drag-icon">
                  <CloudUploadOutlined />
                </p>
                <p className="ant-upload-text">Drop comic page or click to browse</p>
                {currentFile && <Tag color="gold">{currentFile.name}</Tag>}
              </Upload.Dragger>

              <div style={{ marginTop: 16 }}>
                <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
                  Import NOTEtoolsLM <code>lookbook.source_manifest.v1</code>
                </Paragraph>
                <Upload accept=".json,application/json" showUploadList={false} beforeUpload={handleVaultUpload}>
                  <Button block>Import vault manifest</Button>
                </Upload>
              </div>
            </Card>
          </Col>

          <Col xs={24} md={12}>
            <Card title="Pipeline" bordered={false}>
              <Steps
                size="small"
                current={stepIndex}
                items={PIPELINE_STEPS.map((title) => ({ title }))}
                style={{ marginBottom: 16 }}
              />
              {panelCount != null && (
                <Text type="secondary">Last run: {panelCount} panel(s)</Text>
              )}
              {projectId && (
                <div style={{ marginTop: 8 }}>
                  <Text code>{projectId}</Text>
                </div>
              )}
              <Space style={{ marginTop: 16 }} wrap>
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  loading={running}
                  onClick={handleRunPipeline}
                >
                  Run Pipeline
                </Button>
                <Button icon={<ReloadOutlined />} onClick={reset}>
                  Reset
                </Button>
              </Space>
            </Card>
          </Col>
        </Row>

        <Card title="Exports" bordered={false} style={{ marginTop: 16 }}>
          <Space wrap>
            <Button onClick={handleLivingPanels} disabled={!projectId}>
              Living Panels
            </Button>
            <Button onClick={handleExportCineforge} disabled={!projectId}>
              CineForge
            </Button>
            {projectId && (
              <Button type="link" href={`${apiBase}/api/project/${projectId}`} target="_blank">
                Project JSON
              </Button>
            )}
          </Space>
        </Card>
      </Content>

      <Drawer title="Lab settings" open={settingsOpen} onClose={() => setSettingsOpen(false)} width={360}>
        <Form form={form} layout="vertical" initialValues={settings}>
          <Form.Item name="labUrl" label="Lab server URL" rules={[{ required: true }]}>
            <Input placeholder="http://127.0.0.1:8042" />
          </Form.Item>
          <Form.Item name="cineforgeUrl" label="CineForge backend URL" rules={[{ required: true }]}>
            <Input placeholder="http://127.0.0.1:8765" />
          </Form.Item>
          <Form.Item name="quality" label="Quality preset">
            <Input />
          </Form.Item>
          <Form.Item name="vision" label="Vision LLM" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Button type="primary" block onClick={saveSettingsForm}>
            Save
          </Button>
        </Form>
      </Drawer>
    </Layout>
  );
}