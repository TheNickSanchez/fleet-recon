import { ChatView } from '../features/chat/ChatView.tsx';
import { TopBar } from './TopBar.tsx';
import './AppShell.css';

export function App() {
  return (
    <div className="shell">
      <TopBar />
      <main className="shell__body">
        <ChatView />
      </main>
    </div>
  );
}
