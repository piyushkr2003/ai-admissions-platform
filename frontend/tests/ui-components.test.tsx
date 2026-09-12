import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Badge, toneForTemperature } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DataTable } from "@/components/ui/table";

describe("reusable UI components", () => {
  it("renders an empty data-table state", () => {
    render(<DataTable columns={[{ key: "name", header: "Name", render: (row: { name: string }) => row.name }]} data={[]} />);

    expect(screen.getByText("No records found")).toBeInTheDocument();
  });

  it("maps lead temperatures to status tones", () => {
    expect(toneForTemperature("hot")).toBe("danger");
    expect(toneForTemperature("warm")).toBe("warning");
    expect(toneForTemperature("cold")).toBe("info");
  });

  it("renders badges and icon buttons accessibly", () => {
    render(
      <Button icon={<span aria-hidden="true">+</span>}>
        <span>Create</span>
      </Button>,
    );
    render(<Badge tone="success">Active</Badge>);

    expect(screen.getByRole("button", { name: "Create" })).toBeInTheDocument();
    expect(screen.getByText("Active")).toHaveClass("ui-badge--success");
  });

  it("confirms destructive actions through the dialog callbacks", async () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();

    render(
      <ConfirmDialog
        confirmLabel="Archive"
        message="Archive this record?"
        onCancel={onCancel}
        onConfirm={onConfirm}
        open
        title="Confirm archive"
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Archive" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();
  });
});
