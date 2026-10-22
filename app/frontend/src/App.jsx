
import { useState, useRef, useEffect } from 'react';
import './App.css';

const API_BASE = '';

async function apiRequest(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      typeof data.detail === 'string'
        ? data.detail
        : `Request failed (${response.status})`
    );
  }

  return data;
}

function App() {
  const [sessionId, setSessionId] = useState('');
  const [level, setLevel] = useState(1);
  const [attempts, setAttempts] = useState(5);
  const [messagesLeft, setMessagesLeft] = useState(15);
  const [tokensLeft, setTokensLeft] = useState(1000);
  const [messages, setMessages] = useState([]);
  const [prompt, setPrompt] = useState('');
  const [secret, setSecret] = useState('');
  const [notice, setNotice] = useState('');
  const [noticeType, setNoticeType] = useState('info');
  const [loading, setLoading] = useState(false);
  const [secretLoading, setSecretLoading] = useState(false);
  const [started, setStarted] = useState(false);
  const [completed, setCompleted] = useState(false);

  const chatEndRef = useRef(null);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  async function startGame() {
    setLoading(true);
    setNotice('');

    try {
      const data = await apiRequest('/game/start', {});

      setSessionId(data.session_id);
      setLevel(data.current_level);
      setAttempts(data.attempts_left);
      setMessagesLeft(data.messages_left ?? 15);
      setTokensLeft(data.tokens_left ?? 1000);
      setMessages([]);
      setPrompt('');
      setSecret('');
      setStarted(true);
      setCompleted(false);
      setNotice('Game started! Talk to the AI to discover the secret.');
      setNoticeType('success');
    } catch (error) {
      setNotice(`Could not start game: ${error.message}`);
      setNoticeType('error');
    } finally {
      setLoading(false);
    }
  }

  async function sendMessage(event) {
    event.preventDefault();

    const text = prompt.trim();

    if (!text || !sessionId || loading || completed) return;

    const inputTokensUsed = Math.max(1, Math.floor(text.length / 4));

    setMessagesLeft((prev) => Math.max(0, prev - 1));
    setTokensLeft((prev) =>
      Math.max(0, Math.floor(prev - inputTokensUsed))
    );

    setMessages((previous) => [
      ...previous,
      { role: 'user', text },
    ]);

    setPrompt('');
    setLoading(true);
    setNotice('');

    try {
      const data = await apiRequest('/game/chat', {
        session_id: sessionId,
        message: text,
      });

      setMessagesLeft(data.messages_left ?? messagesLeft);
      setTokensLeft(data.tokens_left ?? tokensLeft);

      setMessages((previous) => [
        ...previous,
        {
          role: 'assistant',
          text: data.reply,
        },
      ]);
    } catch (error) {
      setNotice(`Message failed: ${error.message}`);
      setNoticeType('error');
    } finally {
      setLoading(false);
    }
  }

  async function submitSecret(event) {
    event.preventDefault();

    const value = secret.trim();

    if (!value || !sessionId || secretLoading || completed) return;

    setSecretLoading(true);
    setNotice('');

    try {
      const data = await apiRequest('/game/submit-secret', {
        session_id: sessionId,
        secret: value,
      });

      setAttempts(data.attempts_left ?? attempts);

      if (data.messages_left !== undefined) {
        setMessagesLeft(data.messages_left);
      }

      if (data.tokens_left !== undefined) {
        setTokensLeft(data.tokens_left);
      }

      setSecret('');

      if (data.success && data.completed) {
        setCompleted(true);
        setNotice(data.message || 'Challenge completed!');
        setNoticeType('success');
      } else if (data.success) {
        setLevel(data.current_level);
        setAttempts(data.attempts_left);
        setMessagesLeft(data.messages_left ?? 15);
        setTokensLeft(data.tokens_left ?? 1000);
        setMessages([]);
        setNotice(data.message || 'Correct! Next level unlocked.');
        setNoticeType('success');
      } else {
        setNotice(
          `${data.message || 'Incorrect secret.'} Attempts left: ${data.attempts_left}`
        );
        setNoticeType('error');
      }
    } catch (error) {
      setNotice(`Secret submission failed: ${error.message}`);
      setNoticeType('error');
    } finally {
      setSecretLoading(false);
    }
  }

  return (
    <main className="page">
      <section className="hero">
        <p className="eyebrow">PROMPT INJECTION LAB</p>

        <h1>Can you outsmart the robot?</h1>

        <p className="subtitle">
          Talk to the AI, investigate its behavior, and uncover
          each level&apos;s secret to unlock the next challenge.
        </p>
      </section>

      <section className="game-layout">
        {/* LEFT: LEVELS AND PROGRESS */}
        <aside className="sidebar panel">
          <p className="section-label">YOUR PROGRESS</p>

          {[1, 2, 3].map((number) => {
            const unlocked = started && number <= level;

            const passed =
              completed || (started && number < level);

            return (
              <div
                key={number}
                className={`level-item ${
                  level === number && started ? 'active' : ''
                }`}
              >
                <span className="level-number">
                  {passed ? '✓' : number}
                </span>

                <div>
                  <strong>Level {number}</strong>

                  <p>
                    {passed
                      ? 'Completed'
                      : level === number && started
                        ? 'Current challenge'
                        : unlocked
                          ? 'Unlocked'
                          : 'Locked'}
                  </p>
                </div>
              </div>
            );
          })}

          <div className="stats">
            <span>Messages left</span>
            <strong>{started ? messagesLeft : '—'}</strong>
          </div>

          <div className="stats">
            <span>Tokens left</span>
            <strong>{started ? tokensLeft : '—'}</strong>
          </div>

          <button
            className="button secondary full-width"
            onClick={startGame}
            disabled={loading}
          >
            {started ? '↻ Start new game' : 'Start game'}
          </button>

          {started && (
            <p className="small-note">
              Starting a new game creates a new session.
            </p>
          )}
        </aside>

        {/* CENTER: CHAT WITH THE MODEL */}
        <section className="main-panel panel">
          <div className="chat-header">
            <div>
              <p className="section-label">AI CONVERSATION</p>

              <h2>
                {completed
                  ? 'Challenge completed!'
                  : started
                    ? `Level ${level} — Chat with the robot`
                    : 'Ready when you are'}
              </h2>
            </div>

            <span className="level-badge">
              {started ? `LEVEL ${level}` : 'NOT STARTED'}
            </span>
          </div>

          <div className="chat-window" aria-live="polite">
            {!started && (
              <div className="empty-state">
                <div className="robot-icon">🤖</div>

                <h3>Your challenge starts here</h3>

                <button
                  className="button primary"
                  onClick={startGame}
                  disabled={loading}
                >
                  {loading ? 'Starting…' : 'Start challenge'}
                </button>
              </div>
            )}

            {started && messages.length === 0 && !completed && (
              <div className="empty-state">
                <div className="robot-icon">🤖</div>

                <h3>The robot is waiting</h3>

                <p>
                  Send a message to begin investigating this level.
                </p>
              </div>
            )}

            {messages.map((message, index) => (
              <div
                key={`${index}-${message.role}`}
                className={`message-row ${message.role}`}
              >
                <div className="avatar">
                  {message.role === 'user' ? 'You' : 'AI'}
                </div>

                <div className="message">
                  <span className="message-author">
                    {message.role === 'user' ? 'You' : 'Robot'}
                  </span>

                  <p>{message.text}</p>
                </div>
              </div>
            ))}

            {/* AI THINKING INDICATOR */}
            {loading && started && (
              <div className="message-row assistant">
                <div className="avatar">AI</div>

                <div className="message">
                  <span className="message-author">Robot</span>

                  <div
                    className="typing"
                    aria-label="Robot is thinking"
                  >
                    <span className="typing-text">
                      Thinking
                    </span>

                    <span
                      className="typing-dots"
                      aria-hidden="true"
                    >
                      <span>.</span>
                      <span>.</span>
                      <span>.</span>
                    </span>
                  </div>
                </div>
              </div>
            )}

            {completed && (
              <div className="completion">
                <span>🏆</span>
                <h3>You cracked the robot!</h3>
                <p>You completed all three levels.</p>
              </div>
            )}

            <div ref={chatEndRef} />
          </div>

          <form className="chat-form" onSubmit={sendMessage}>
            <div className="input-wrapper">
              <textarea
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder={
                  started
                    ? 'Write a message to the robot…'
                    : 'Start a game to send messages'
                }
                rows={1}
                disabled={!started || loading || completed}
              />

              <button
                className="button primary send-icon-btn"
                type="submit"
                disabled={
                  !started ||
                  loading ||
                  completed ||
                  !prompt.trim()
                }
                title="Send message"
              >
                ↑
              </button>
            </div>
          </form>
        </section>

        {/* RIGHT: SECRET INPUT AND SUBMISSION */}
        <aside className="secret-panel panel">
          <form className="secret-form" onSubmit={submitSecret}>
            <div className="secret-top-section">
              <div>
                <p className="section-label">SECRET VALIDATION</p>

                <h3>Unlock the next level</h3>

                <p className="small-note">
                  Submit the secret you discovered in the conversation.
                </p>
              </div>

              <div className="secret-stats">
                <span>Attempts left</span>
                <strong>{started ? attempts : '—'}</strong>
              </div>
            </div>

            <div className="secret-bottom-section">
              {notice && (
                <div
                  className={`notice ${noticeType}`}
                  role="status"
                  style={{ marginBottom: '12px' }}
                >
                  {notice}
                </div>
              )}

              <div className="secret-input-row">
                <input
                  value={secret}
                  onChange={(event) => setSecret(event.target.value)}
                  placeholder="Enter secret…"
                  disabled={
                    !started || secretLoading || completed
                  }
                />

                <button
                  className="button secondary"
                  type="submit"
                  disabled={
                    !started ||
                    secretLoading ||
                    completed ||
                    !secret.trim()
                  }
                >
                  {secretLoading ? 'Checking…' : 'Check secret'}
                </button>
              </div>
            </div>
          </form>
        </aside>
      </section>
    </main>
  );
}

export default App;
