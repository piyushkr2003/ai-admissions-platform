import type { ApiClient } from "@/lib/api/client";
import type { AuthResponse, LoginRequest } from "@/types/auth";

export const authApi = {
  login(client: ApiClient, payload: LoginRequest) {
    return client.post<AuthResponse>("/auth/login", payload);
  },
  refresh(client: ApiClient, refreshToken: string) {
    return client.post<AuthResponse>("/auth/refresh", { refresh_token: refreshToken });
  },
  logout(client: ApiClient, refreshToken: string | null) {
    return client.post<{ success: boolean }>("/auth/logout", { refresh_token: refreshToken });
  },
  me(client: ApiClient) {
    return client.get<AuthResponse["user"]>("/auth/me");
  },
};
