import { LoginForm } from "@/features/auth/login-form";

export default function LoginPage() {
  return (
    <main className="login-page">
      <div className="login-page__copy">
        <span className="eyebrow">AI Admissions Platform</span>
        <h1>Admissions Operations</h1>
        <p>Secure access for college admissions teams.</p>
      </div>
      <LoginForm />
    </main>
  );
}
