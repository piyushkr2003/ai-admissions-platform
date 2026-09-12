export type RequestMeta = {
  request_id: string;
  page?: number;
  page_size?: number;
  total?: number;
  total_pages?: number;
};

export type ApiEnvelope<T> = {
  data: T;
  meta: RequestMeta;
};

export type ApiErrorBody = {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    request_id?: string;
  };
};

export type PaginationParams = {
  page?: number;
  page_size?: number;
};
