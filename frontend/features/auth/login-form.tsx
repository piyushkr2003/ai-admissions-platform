"use client";

import { FormEvent, useState } from "react";
import { LogIn } from "lucide-react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FormField, TextInput } from "@/components/ui/form";
import { ErrorState } from "@/components/ui/state";
import { useAuth } from "@/features/auth/auth-provider";

export function LoginForm() {
  const router = useRouter();
  const { error, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setLocalError(null);
    try {
      await login({ email, password });
      router.replace("/dashboard");
    } catch (submitError) {
      setLocalError(submitError instanceof Error ? submitError.message : "Unable to sign in.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="login-card" title="Admin Sign In" subtitle="Access the admissions dashboard">
      <form className="login-form" onSubmit={handleSubmit}>
        <FormField label="Email" htmlFor="email">
          <TextInput
            autoComplete="email"
            id="email"
            name="email"
            onChange={(event) => setEmail(event.target.value)}
            required
            type="email"
            value={email}
          />
        </FormField>
        <FormField label="Password" htmlFor="password">
          <TextInput
            autoComplete="current-password"
            id="password"
            name="password"
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
        </FormField>
        {localError || error ? (
          <ErrorState title="Sign in failed" message={localError ?? error ?? undefined} />
        ) : null}
        <Button disabled={submitting} icon={<LogIn size={16} aria-hidden="true" />} type="submit">
          {submitting ? "Signing in" : "Sign in"}
        </Button>
      </form>
    </Card>
  );
}
