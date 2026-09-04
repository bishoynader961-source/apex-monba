/**
 * Email reporting API client — daily sales reports via SMTP.
 */
import { api } from "@/lib/api";

export interface EmailHealthResponse {
  smtp_configured: boolean;
  smtp_host: string;
  smtp_port: number;
  smtp_tls: boolean;
  from_email: string;
}

export interface DailyReportRequest {
  to_email: string;
  report_date?: string;
}

export interface DailyReportResponse {
  sent: boolean;
  message: string;
}

export async function getEmailHealth(): Promise<EmailHealthResponse> {
  const { data } = await api.get<EmailHealthResponse>("/api/v1/email/health");
  return data;
}

export async function sendDailySalesReport(
  payload: DailyReportRequest,
): Promise<DailyReportResponse> {
  const { data } = await api.post<DailyReportResponse>(
    "/api/v1/email/daily-sales",
    payload,
  );
  return data;
}
