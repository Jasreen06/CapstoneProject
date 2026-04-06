import { useState, useRef, useEffect } from 'react';
import { postJSON } from '../api/client.js';
import { SUGGESTED_QUESTIONS } from '../utils/constants.js';
import { Send, Bot, User, MessageSquare } from 'lucide-react';

function Message({ msg }) {
  const isUser = msg.role === 'user';
  return (
    <div className={`flex gap-2 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center shrink-0 mt-0.5">
          <Bot size={14} className="text-white" />
        </div>
      )}
      <div
        className={`max-w-[80%] rounded-lg px-3 py-2 text-sm leading-relaxed ${
          isUser
            ? 'bg-blue-600 text-white'
            : 'bg-slate-700 text-slate-100 border border-slate-600'
        }`}
        style={{ whiteSpace: 'pre-wrap' }}
      >
        {msg.content}
      </div>
      {isUser && (
        <div className="w-7 h-7 rounded-full bg-slate-600 flex items-center justify-center shrink-0 mt-0.5">
          <User size={14} className="text-white" />
        </div>
      )}
    </div>
  );
}

export default function AIAdvisor() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: 'Hello! I\'m DockWise AI, your maritime intelligence advisor. I have access to live vessel tracking, port congestion data, and chokepoint analytics. How can I help you today?',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async (text) => {
    const msg = text || input.trim();
    if (!msg || loading) return;

    const userMsg = { role: 'user', content: msg };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    // Build history for API (exclude the latest user message we just added)
    const history = messages.map(m => ({ role: m.role, content: m.content }));

    try {
      const res = await postJSON('/api/chat/', {
        message: msg,
        history,
      });
      setMessages(prev => [...prev, { role: 'assistant', content: res.response }]);
    } catch (e) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${e.message}. Please check that the backend is running and GROQ_API_KEY is configured.`,
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 56px)' }}>
      {/* Header */}
      <div className="p-4 border-b border-slate-700 flex items-center gap-2">
        <MessageSquare size={18} className="text-blue-400" />
        <div>
          <h2 className="text-sm font-bold text-white">AI Maritime Advisor</h2>
          <p className="text-xs text-slate-400">Powered by Groq LLaMA-3.3-70B + live maritime data</p>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.map((msg, i) => (
          <Message key={i} msg={msg} />
        ))}
        {loading && (
          <div className="flex gap-2 items-center text-slate-400 text-sm">
            <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center shrink-0">
              <Bot size={14} className="text-white" />
            </div>
            <div className="flex gap-1">
              <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Suggested questions */}
      {messages.length <= 1 && (
        <div className="px-4 pb-2">
          <p className="text-xs text-slate-500 mb-2">Suggested questions:</p>
          <div className="flex flex-wrap gap-2">
            {SUGGESTED_QUESTIONS.map((q, i) => (
              <button
                key={i}
                onClick={() => sendMessage(q)}
                className="text-xs px-2 py-1 rounded bg-slate-700 text-slate-300 hover:bg-slate-600 hover:text-white transition-colors border border-slate-600"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="p-4 border-t border-slate-700">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about port congestion, vessel rerouting, chokepoint disruptions..."
            rows={2}
            className="flex-1 bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500 resize-none"
          />
          <button
            onClick={() => sendMessage()}
            disabled={!input.trim() || loading}
            className="px-4 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:cursor-not-allowed text-white rounded-lg flex items-center justify-center transition-colors"
          >
            <Send size={16} />
          </button>
        </div>
        <p className="text-xs text-slate-600 mt-1">Press Enter to send, Shift+Enter for newline</p>
      </div>
    </div>
  );
}
