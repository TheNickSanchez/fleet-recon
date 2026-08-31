// Global styles must be imported before feature modules so that component
// stylesheets win over the base primitives at equal specificity.
import './styles/tokens.css';
import './styles/base.css';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from './app/App.tsx';
import { AppStateProvider } from './app/AppState.tsx';
import { ToastProvider } from './components/Toast.tsx';

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 1000, retry: 1 } },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AppStateProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </AppStateProvider>
    </QueryClientProvider>
  </StrictMode>,
);
