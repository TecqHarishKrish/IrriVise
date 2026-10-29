import * as React from 'react';
import { flexRender, getCoreRowModel, getPaginationRowModel, getSortedRowModel, useReactTable, type ColumnDef, type SortingState } from '@tanstack/react-table';
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Download } from 'lucide-react';
import { downloadText, toCsv } from '@/lib/utils';
import { Button } from './ui/button';

export function DataTable<T extends object>({ data, columns, pageSize = 10, caption, exportName, onRowClick, rowLabel }: {
  data: T[]; columns: ColumnDef<T, unknown>[]; pageSize?: number; caption: string; exportName?: string; onRowClick?: (row: T) => void; rowLabel?: (row: T) => string;
}) {
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const table = useReactTable({ data, columns, state: { sorting }, onSortingChange: setSorting, getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(), getPaginationRowModel: getPaginationRowModel(), initialState: { pagination: { pageSize } } });
  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="bg-muted/60 text-left text-xs uppercase tracking-wide text-muted-foreground">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => (
                  <th key={h.id} scope="col" className="whitespace-nowrap px-3 py-2 font-medium" aria-sort={h.column.getIsSorted() === 'asc' ? 'ascending' : h.column.getIsSorted() === 'desc' ? 'descending' : 'none'}>
                    {h.isPlaceholder ? null : h.column.getCanSort() ? (
                      <button type="button" className="inline-flex items-center gap-1 hover:text-foreground" onClick={h.column.getToggleSortingHandler()}>
                        {flexRender(h.column.columnDef.header, h.getContext())}
                        {h.column.getIsSorted() === 'asc' ? <ArrowUp className="size-3" /> : h.column.getIsSorted() === 'desc' ? <ArrowDown className="size-3" /> : null}
                      </button>
                    ) : flexRender(h.column.columnDef.header, h.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className={onRowClick ? 'cursor-pointer border-t hover:bg-muted/50 focus-within:bg-muted/50' : 'border-t'}
                onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                onKeyDown={onRowClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onRowClick(row.original); } } : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                aria-label={onRowClick && rowLabel ? rowLabel(row.original) : undefined}
              >
                {row.getVisibleCells().map((cell) => <td key={cell.id} className="tabular whitespace-nowrap px-3 py-2">{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}
              </tr>
            ))}
            {!data.length && <tr><td colSpan={columns.length} className="px-3 py-6 text-center text-muted-foreground">No rows.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>{data.length} row(s){table.getPageCount() > 1 ? ` · page ${table.getState().pagination.pageIndex + 1} of ${table.getPageCount()}` : ''}</span>
        <div className="flex gap-1">
          {exportName && <Button variant="ghost" size="sm" onClick={() => downloadText(`${exportName}.csv`, toCsv(data as Record<string, unknown>[]), 'text/csv')}><Download aria-hidden />CSV</Button>}
          {table.getPageCount() > 1 && (
            <>
              <Button variant="outline" size="icon" className="size-8" aria-label="Previous page" disabled={!table.getCanPreviousPage()} onClick={() => table.previousPage()}><ChevronLeft /></Button>
              <Button variant="outline" size="icon" className="size-8" aria-label="Next page" disabled={!table.getCanNextPage()} onClick={() => table.nextPage()}><ChevronRight /></Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
