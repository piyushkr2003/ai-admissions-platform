export type BreakdownSlice = {
  label: string;
  value: string;
  count: number | null;
};

export type BreakdownGroup = {
  key: string;
  title: string;
  available: boolean;
  slices: BreakdownSlice[];
  total: number | null;
};

export type ConversionMetric = {
  key: string;
  label: string;
  rate: number | null;
  numeratorLabel: string;
  denominatorLabel: string;
};

export type AnalyticsOverview = {
  groups: BreakdownGroup[];
  conversions: ConversionMetric[];
};
