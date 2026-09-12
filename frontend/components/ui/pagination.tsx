import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

type PaginationProps = {
  page: number;
  pageSize: number;
  total?: number;
  totalPages?: number;
  onPageChange: (page: number) => void;
};

export function Pagination({ page, pageSize, total, totalPages, onPageChange }: PaginationProps) {
  const pages = totalPages ?? (total ? Math.max(1, Math.ceil(total / pageSize)) : 1);
  return (
    <nav className="pagination" aria-label="Pagination">
      <Button
        aria-label="Previous page"
        disabled={page <= 1}
        icon={<ChevronLeft size={16} aria-hidden="true" />}
        onClick={() => onPageChange(page - 1)}
        variant="secondary"
      >
        Previous
      </Button>
      <span aria-live="polite">
        Page {page} of {pages}
      </span>
      <Button
        aria-label="Next page"
        disabled={page >= pages}
        icon={<ChevronRight size={16} aria-hidden="true" />}
        onClick={() => onPageChange(page + 1)}
        variant="secondary"
      >
        Next
      </Button>
    </nav>
  );
}
