"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FormField, SelectInput, TextArea, TextInput } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { ApiError } from "@/lib/api/client";
import { knowledgeApi } from "@/lib/api/knowledge";

const SUPPORTED_TYPES = [
  { value: "faq", label: "FAQ", needsText: true },
  { value: "manual", label: "Manual Note", needsText: true },
  { value: "txt", label: "Plain Text", needsText: true },
  { value: "pdf", label: "PDF File", needsText: false },
] as const;

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      resolve(result.split(",").pop() ?? "");
    };
    reader.onerror = () => reject(reader.error ?? new Error("Failed to read file."));
    reader.readAsDataURL(file);
  });
}

export function CreateSourceForm({ onCreated }: { onCreated: () => void }) {
  const { apiClient } = useAuth();
  const { collegeId } = useTenant();
  const { notify } = useToast();
  const [name, setName] = useState("");
  const [sourceType, setSourceType] = useState<(typeof SUPPORTED_TYPES)[number]["value"]>("faq");
  const [text, setText] = useState("");
  const [visibility, setVisibility] = useState<"public" | "internal">("public");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const needsText = SUPPORTED_TYPES.find((type) => type.value === sourceType)?.needsText ?? true;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const payload: Parameters<typeof knowledgeApi.createSource>[2] = {
        name,
        source_type: sourceType,
        visibility,
      };
      if (needsText) {
        payload.text = text;
      } else {
        const file = fileInputRef.current?.files?.[0];
        if (!file) {
          throw new Error("Choose a PDF file to upload.");
        }
        payload.file_base64 = await readFileAsBase64(file);
      }
      await knowledgeApi.createSource(apiClient, collegeId, payload);
      notify("success", "Knowledge source ingested.");
      setName("");
      setText("");
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      onCreated();
    } catch (submitError) {
      const message = submitError instanceof ApiError ? submitError.message : (submitError as Error).message;
      setError(message);
      notify("error", message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card subtitle="Text-based sources (FAQ, manual notes, plain text) and PDF files are supported. DOCX, CSV/XLSX, and website import are not yet implemented on the backend." title="Add Knowledge Source">
      <form className="login-form" onSubmit={handleSubmit}>
        <FormField htmlFor="source-name" label="Name">
          <TextInput id="source-name" onChange={(event) => setName(event.target.value)} required value={name} />
        </FormField>
        <FormField htmlFor="source-type" label="Type">
          <SelectInput
            id="source-type"
            onChange={(event) => setSourceType(event.target.value as typeof sourceType)}
            value={sourceType}
          >
            {SUPPORTED_TYPES.map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </SelectInput>
        </FormField>
        <FormField htmlFor="source-visibility" label="Visibility">
          <SelectInput
            id="source-visibility"
            onChange={(event) => setVisibility(event.target.value as typeof visibility)}
            value={visibility}
          >
            <option value="public">Public (used in agent answers)</option>
            <option value="internal">Internal (staff reference only)</option>
          </SelectInput>
        </FormField>
        {needsText ? (
          <FormField htmlFor="source-text" label="Content">
            <TextArea id="source-text" onChange={(event) => setText(event.target.value)} required value={text} />
          </FormField>
        ) : (
          <FormField htmlFor="source-file" label="PDF file">
            <input accept="application/pdf" id="source-file" ref={fileInputRef} required type="file" />
          </FormField>
        )}
        {error ? <p className="form-field__error">{error}</p> : null}
        <Button disabled={busy} type="submit">
          {busy ? "Ingesting" : "Add source"}
        </Button>
      </form>
    </Card>
  );
}
