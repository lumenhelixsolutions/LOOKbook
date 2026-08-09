import type { ThemeConfig } from 'antd';
import { theme } from 'antd';

export const PORTFOLIO = {
  accent: '#ffb042',
  surface: '#12100e',
  text: '#f5e6d0',
  muted: 'rgba(245, 230, 208, 0.55)',
  bg: '#06090e',
  card: '#121826',
  border: '#1e2538',
} as const;

export const portfolioTheme: ThemeConfig = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: PORTFOLIO.accent,
    colorInfo: PORTFOLIO.accent,
    colorBgBase: PORTFOLIO.bg,
    colorBgContainer: PORTFOLIO.card,
    colorBgElevated: PORTFOLIO.surface,
    colorText: PORTFOLIO.text,
    colorTextSecondary: PORTFOLIO.muted,
    colorBorder: PORTFOLIO.border,
    colorBorderSecondary: PORTFOLIO.border,
    borderRadius: 10,
    fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif",
    fontSize: 14,
  },
  components: {
    Layout: {
      headerBg: PORTFOLIO.surface,
      bodyBg: PORTFOLIO.bg,
    },
    Card: {
      colorBgContainer: PORTFOLIO.card,
    },
    Button: {
      primaryShadow: 'none',
    },
  },
};