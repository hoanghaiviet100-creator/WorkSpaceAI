import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { ArrowLeft, ArrowRight, Eye, EyeOff, Info } from "lucide-react";
import { Brand, ThemeControl } from "./components";

export type AuthMode = "signin" | "signup" | "reset";
type Provider = "Google" | "Microsoft" | "Apple";
type FieldErrors = Partial<Record<"name" | "email" | "password", string>>;
type Feedback = { scope: "provider" | "form"; title: string; detail: string };

const copy = {
  signin: {
    title: "Sign in to WorkspaceAI",
    description: "Pick up where your research left off.",
    submit: "Sign in",
  },
  signup: {
    title: "Create your account",
    description: "A shared space for your sources, ideas and next steps.",
    submit: "Create account",
  },
  reset: {
    title: "Reset your password",
    description: "Enter the email address you use for your workspace.",
    submit: "Send reset link",
  },
};

export default function Auth({
  mode,
  onModeChange,
  onClose,
  onHome,
  onPreview,
}: {
  mode: AuthMode;
  onModeChange: (mode: AuthMode) => void;
  onClose: () => void;
  onHome: () => void;
  onPreview: () => void;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const form = useRef<HTMLFormElement>(null);
  const feedbackRef = useRef<HTMLDivElement>(null);
  const fieldId = useId();
  const text = copy[mode];

  useEffect(() => {
    setPassword("");
    setShowPassword(false);
    setErrors({});
    setFeedback(null);
    heading.current?.focus({ preventScroll: true });
    document.title = `${copy[mode].title} · WorkspaceAI`;
    return () => {
      document.title = "WorkspaceAI";
    };
  }, [mode]);
  useEffect(() => {
    if (feedback) feedbackRef.current?.scrollIntoView({ block: "nearest" });
  }, [feedback]);

  const edit = (field: keyof FieldErrors) => {
    setErrors((current) => ({ ...current, [field]: undefined }));
    setFeedback(null);
  };
  const providerSignIn = (provider: Provider) => {
    setFeedback({
      scope: "provider",
      title: `${provider} sign-in is not available in this preview.`,
      detail:
        "You can explore the demo workspace while accounts are being connected.",
    });
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const next: FieldErrors = {};
    if (mode === "signup" && !name.trim()) next.name = "Enter your name.";
    const emailInput = form.current?.elements.namedItem(
      "email",
    ) as HTMLInputElement;
    if (!email.trim()) next.email = "Enter your email address.";
    else if (emailInput.validity.typeMismatch)
      next.email = "Enter a valid email address.";
    if (mode !== "reset") {
      if (!password) next.password = "Enter your password.";
      else if (mode === "signup" && password.length < 12)
        next.password = "Use at least 12 characters.";
    }
    setErrors(next);
    setFeedback(null);
    const first = Object.keys(next)[0];
    if (first) {
      (form.current?.elements.namedItem(first) as HTMLElement)?.focus();
      return;
    }
    // This frontend has no identity service. Never manufacture an account,
    // session, successful sign-in or a password-reset delivery.
    setPassword("");
    setFeedback({
      scope: "form",
      title:
        mode === "reset"
          ? "Password reset is not available in this preview."
          : mode === "signup"
            ? "Account creation is not available in this preview."
            : "Email sign-in is not available in this preview.",
      detail:
        mode === "reset"
          ? "No reset email was sent. You can return to sign-in or explore the demo workspace."
          : "Your password was not sent or saved. Use the demo workspace to explore the app.",
    });
  };
  const message = feedback && (
    <div className="auth-feedback" role="status" ref={feedbackRef}>
      <Info size={17} />
      <div>
        <strong>{feedback.title}</strong>
        <p>{feedback.detail}</p>
      </div>
    </div>
  );

  return (
    <div className="auth-screen">
      <header className="auth-header">
        <Brand onClick={onHome} />
        <div className="auth-header-actions">
          <button
            className="auth-back"
            aria-label="Back to workspace"
            title="Back to workspace"
            onClick={onClose}
          >
            <ArrowLeft size={15} />
            <span>Back to workspace</span>
          </button>
          <ThemeControl />
        </div>
      </header>
      <main className="auth-main" id="main-content">
        <div className="auth-container">
          <section className="auth-card" aria-labelledby="auth-title">
            <div className="auth-intro">
              <h1 id="auth-title" tabIndex={-1} ref={heading}>
                {text.title}
              </h1>
              <p>{text.description}</p>
            </div>
            <p className="auth-preview-note">
              <Info size={14} />
              Sign-in preview · Accounts are not connected yet.
            </p>
            {feedback?.scope === "provider" && message}
            {mode !== "reset" && (
              <>
                <div
                  className="auth-providers"
                  role="group"
                  aria-label="Sign-in methods"
                >
                  {(["Google", "Microsoft", "Apple"] as const).map(
                    (provider) => (
                      <button
                        type="button"
                        className={`auth-provider provider-${provider.toLowerCase()}`}
                        key={provider}
                        onClick={() => providerSignIn(provider)}
                      >
                        <ProviderIcon provider={provider} />
                        <span>
                          {provider === "Microsoft"
                            ? "Sign in with Microsoft"
                            : `Continue with ${provider}`}
                        </span>
                      </button>
                    ),
                  )}
                </div>
                <div className="auth-divider">
                  <span>or use your email</span>
                </div>
              </>
            )}
            <form className="auth-form" ref={form} onSubmit={submit} noValidate>
              {mode === "signup" && (
                <div className="auth-field">
                  <label htmlFor={`${fieldId}-name`}>Full name</label>
                  <input
                    id={`${fieldId}-name`}
                    name="name"
                    autoComplete="name"
                    value={name}
                    maxLength={100}
                    required
                    placeholder="Your full name"
                    aria-invalid={!!errors.name}
                    aria-describedby={
                      errors.name ? `${fieldId}-name-error` : undefined
                    }
                    onChange={(event) => {
                      setName(event.target.value);
                      edit("name");
                    }}
                  />
                  {errors.name && (
                    <p
                      className="auth-field-error"
                      id={`${fieldId}-name-error`}
                      role="alert"
                    >
                      {errors.name}
                    </p>
                  )}
                </div>
              )}
              <div className="auth-field">
                <label htmlFor={`${fieldId}-email`}>Email address</label>
                <input
                  id={`${fieldId}-email`}
                  name="email"
                  type="email"
                  autoComplete={mode === "signin" ? "username" : "email"}
                  inputMode="email"
                  value={email}
                  maxLength={254}
                  required
                  autoCapitalize="none"
                  spellCheck={false}
                  placeholder="you@university.edu"
                  aria-invalid={!!errors.email}
                  aria-describedby={
                    errors.email ? `${fieldId}-email-error` : undefined
                  }
                  onChange={(event) => {
                    setEmail(event.target.value);
                    edit("email");
                  }}
                />
                {errors.email && (
                  <p
                    className="auth-field-error"
                    id={`${fieldId}-email-error`}
                    role="alert"
                  >
                    {errors.email}
                  </p>
                )}
              </div>
              {mode !== "reset" && (
                <div className="auth-field">
                  <label htmlFor={`${fieldId}-password`}>Password</label>
                  <div
                    className="auth-password"
                    data-invalid={!!errors.password}
                  >
                    <input
                      id={`${fieldId}-password`}
                      name="password"
                      type={showPassword ? "text" : "password"}
                      autoComplete={
                        mode === "signup" ? "new-password" : "current-password"
                      }
                      required
                      value={password}
                      maxLength={256}
                      placeholder={
                        mode === "signup"
                          ? "Create a password"
                          : "Enter your password"
                      }
                      aria-invalid={!!errors.password}
                      aria-describedby={
                        errors.password
                          ? `${fieldId}-password-error`
                          : mode === "signup"
                            ? `${fieldId}-password-hint`
                            : undefined
                      }
                      onChange={(event) => {
                        setPassword(event.target.value);
                        edit("password");
                      }}
                    />
                    <button
                      type="button"
                      aria-label={
                        showPassword ? "Hide password" : "Show password"
                      }
                      aria-pressed={showPassword}
                      onClick={() => setShowPassword(!showPassword)}
                    >
                      {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                  {errors.password ? (
                    <p
                      className="auth-field-error"
                      id={`${fieldId}-password-error`}
                      role="alert"
                    >
                      {errors.password}
                    </p>
                  ) : (
                    mode === "signup" && (
                      <p
                        className="auth-field-hint"
                        id={`${fieldId}-password-hint`}
                      >
                        Use at least 12 characters.
                      </p>
                    )
                  )}
                </div>
              )}
              {mode === "signin" && (
                <div className="auth-options">
                  <label>
                    <input
                      type="checkbox"
                      checked={remember}
                      onChange={(event) => setRemember(event.target.checked)}
                    />
                    Keep me signed in
                  </label>
                  <a
                    href="#forgot-password"
                    onClick={(event) => {
                      event.preventDefault();
                      onModeChange("reset");
                    }}
                  >
                    Forgot password?
                  </a>
                </div>
              )}
              {feedback?.scope === "form" && message}
              <button className="button primary auth-submit" type="submit">
                {text.submit}
                <ArrowRight size={16} />
              </button>
            </form>
            <div className="auth-switch">
              {mode === "signin" ? (
                <>
                  <span>New to WorkspaceAI?</span>
                  <a
                    href="#signup"
                    onClick={(event) => {
                      event.preventDefault();
                      onModeChange("signup");
                    }}
                  >
                    Create an account
                  </a>
                </>
              ) : mode === "signup" ? (
                <>
                  <span>Already have an account?</span>
                  <a
                    href="#login"
                    onClick={(event) => {
                      event.preventDefault();
                      onModeChange("signin");
                    }}
                  >
                    Sign in
                  </a>
                </>
              ) : (
                <a
                  href="#login"
                  onClick={(event) => {
                    event.preventDefault();
                    onModeChange("signin");
                  }}
                >
                  <ArrowLeft size={14} />
                  Back to sign in
                </a>
              )}
            </div>
          </section>
          <button className="auth-demo-link" onClick={onPreview}>
            Explore demo workspace
            <ArrowRight size={15} />
          </button>
        </div>
      </main>
    </div>
  );
}

function ProviderIcon({ provider }: { provider: Provider }) {
  if (provider === "Google")
    return (
      <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
        <path
          fill="#4285F4"
          d="M22.56 12.25c0-.73-.06-1.42-.19-2.09H12v3.96h5.92a5.07 5.07 0 0 1-2.2 3.32v2.76h3.57c2.08-1.92 3.27-4.75 3.27-7.95Z"
        />
        <path
          fill="#34A853"
          d="M12 23c2.97 0 5.46-.98 7.28-2.8l-3.57-2.76c-.98.66-2.24 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z"
        />
        <path
          fill="#FBBC05"
          d="M5.84 13.97A6.6 6.6 0 0 1 5.5 12c0-.69.12-1.35.34-1.97V7.19H2.18A11 11 0 0 0 1 12c0 1.78.43 3.47 1.18 4.81l3.66-2.84Z"
        />
        <path
          fill="#EA4335"
          d="M12 5.5c1.62 0 3.06.56 4.21 1.64l3.16-3.16A10.56 10.56 0 0 0 12 1a11 11 0 0 0-9.82 6.19l3.66 2.84C6.71 7.43 9.14 5.5 12 5.5Z"
        />
      </svg>
    );
  if (provider === "Microsoft")
    return (
      <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
        <path fill="#F25022" d="M1 1h10.5v10.5H1z" />
        <path fill="#7FBA00" d="M12.5 1H23v10.5H12.5z" />
        <path fill="#00A4EF" d="M1 12.5h10.5V23H1z" />
        <path fill="#FFB900" d="M12.5 12.5H23V23H12.5z" />
      </svg>
    );
  // Apple mark from Simple Icons (CC0); provider trademarks belong to Apple.
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M12.152 6.896c-.948 0-2.415-1.078-3.96-1.04-2.04.027-3.91 1.183-4.961 3.014-2.117 3.675-.546 9.103 1.519 12.09 1.013 1.454 2.208 3.09 3.792 3.039 1.52-.065 2.09-.987 3.935-.987 1.831 0 2.35.987 3.96.948 1.637-.026 2.676-1.48 3.676-2.948 1.156-1.688 1.636-3.325 1.662-3.415-.039-.013-3.182-1.221-3.22-4.857-.026-3.04 2.48-4.494 2.597-4.559-1.429-2.09-3.623-2.324-4.39-2.376-2-.156-3.675 1.09-4.61 1.09zM15.53 3.83c.843-1.012 1.4-2.427 1.245-3.83-1.207.052-2.662.805-3.532 1.818-.78.896-1.454 2.338-1.273 3.714 1.338.104 2.715-.688 3.559-1.701" />
    </svg>
  );
}
