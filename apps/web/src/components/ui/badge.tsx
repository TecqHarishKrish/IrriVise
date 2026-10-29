import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva('inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium [&_svg]:size-3', {
  variants: {
    variant: {
      default: 'border-transparent bg-secondary text-secondary-foreground',
      primary: 'border-transparent bg-primary text-primary-foreground',
      outline: 'text-foreground',
      warning: 'border-warning/30 bg-warning-soft text-warning',
      destructive: 'border-destructive/30 bg-destructive-soft text-destructive',
      success: 'border-success/30 bg-success-soft text-success',
      info: 'border-transparent bg-accent text-accent-foreground',
    },
  },
  defaultVariants: { variant: 'default' },
});

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
