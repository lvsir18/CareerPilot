import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AppointmentForm } from "@/components/appointment-form";
import type { ApplicationEvent } from "@/lib/api";

const add = vi.hoisted(() => vi.fn());
vi.mock("@/lib/client-api", () => ({ addApplicationEvent: add }));
function appointment(id: string, day: string): ApplicationEvent {
  return { id, application_id: "app", previous_status: "applied", new_status: "interview",
    from_status: "applied", to_status: "interview", event_time: `2026-10-${day}T06:30:00Z`,
    created_at: "", actor: "user", evidence_type: "manual", source_type: "manual",
    source_reference: null, evidence_summary: null, verification_status: "user_reported",
    note: id === "first" ? "一面" : "二面", is_scheduled: true, superseded_at: null };
}
const rounds = [appointment("first", "26"), appointment("second", "29")];
beforeEach(() => { add.mockReset(); add.mockResolvedValue({ ok: true, data: rounds[0] }); });
afterEach(cleanup);
it("多轮预约必须明确选择改期目标，不能静默替换全部", () => {
  render(<AppointmentForm applicationId="app" appointments={rounds} />);
  fireEvent.change(screen.getByLabelText("发生时间"), { target: { value: "2026-10-28T14:30" } });
  fireEvent.submit(screen.getByRole("button", { name: "保存改期" }).closest("form")!);
  expect(screen.getByText("请选择要改期的具体预约，其他轮次将保留")).toBeVisible();
  expect(add).not.toHaveBeenCalled();
});
it("只发送所选预约 id，其他轮次不作为改期目标", async () => {
  const saved = vi.fn();
  render(<AppointmentForm applicationId="app" appointments={rounds} onSaved={saved} />);
  fireEvent.change(screen.getByLabelText("要改期的预约"), { target: { value: "first" } });
  fireEvent.change(screen.getByLabelText("发生时间"), { target: { value: "2026-10-28T14:30" } });
  fireEvent.click(screen.getByRole("button", { name: "保存改期" }));
  await waitFor(() => expect(saved).toHaveBeenCalledOnce());
  expect(add).toHaveBeenCalledWith("app", expect.objectContaining({ reschedule_event_id: "first" }));
  expect(add.mock.calls[0]![1]).not.toHaveProperty("supersede_scheduled");
});
