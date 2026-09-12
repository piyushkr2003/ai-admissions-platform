"use client";

import { Tabs } from "@/components/ui/tabs";
import { FormField, TextInput } from "@/components/ui/form";
import { DATE_RANGE_PRESETS } from "@/lib/analytics/date-range";
import type { AnalyticsDateRangePreset } from "@/types/analytics";

export function DateRangeSelector({
  preset,
  customStart,
  customEnd,
  validationError,
  onPresetChange,
  onCustomStartChange,
  onCustomEndChange,
}: {
  preset: AnalyticsDateRangePreset;
  customStart: string;
  customEnd: string;
  validationError: string | null;
  onPresetChange: (preset: AnalyticsDateRangePreset) => void;
  onCustomStartChange: (value: string) => void;
  onCustomEndChange: (value: string) => void;
}) {
  return (
    <div className="date-range-bar">
      <Tabs
        activeKey={preset}
        onChange={(key) => onPresetChange(key as AnalyticsDateRangePreset)}
        tabs={DATE_RANGE_PRESETS}
      />
      {preset === "custom" ? (
        <div className="date-range-bar__custom">
          <FormField error={validationError ?? undefined} htmlFor="analytics-start-date" label="Start date">
            <TextInput
              id="analytics-start-date"
              max={customEnd || undefined}
              onChange={(event) => onCustomStartChange(event.target.value)}
              type="date"
              value={customStart}
            />
          </FormField>
          <FormField htmlFor="analytics-end-date" label="End date">
            <TextInput
              id="analytics-end-date"
              min={customStart || undefined}
              onChange={(event) => onCustomEndChange(event.target.value)}
              type="date"
              value={customEnd}
            />
          </FormField>
        </div>
      ) : null}
    </div>
  );
}
