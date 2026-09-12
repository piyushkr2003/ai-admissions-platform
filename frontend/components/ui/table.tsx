import type { ReactNode } from "react";
import { EmptyState } from "@/components/ui/state";

export type DataTableColumn<T> = {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  align?: "left" | "right" | "center";
};

export function DataTable<T>({
  columns,
  data,
  emptyTitle = "No records found",
}: {
  columns: DataTableColumn<T>[];
  data: T[];
  emptyTitle?: string;
}) {
  if (data.length === 0) {
    return <EmptyState title={emptyTitle} />;
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th className={column.align ? `align-${column.align}` : undefined} key={column.key} scope="col">
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {columns.map((column) => (
                <td className={column.align ? `align-${column.align}` : undefined} key={column.key}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
