import React from 'react';
import ReactDOM from 'react-dom/client';
import { ConfigProvider } from 'antd';
import App from './App';
import { portfolioTheme } from './theme/portfolio';
import 'antd/dist/reset.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider theme={portfolioTheme}>
      <App />
    </ConfigProvider>
  </React.StrictMode>,
);