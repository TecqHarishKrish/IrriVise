import { Link } from 'react-router-dom';
import { Compass } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/common';

export default function NotFound() {
  return <EmptyState icon={Compass} title="Page not found" description="This address does not match any IrriVise page." action={<Button asChild><Link to="/">Back to Command Center</Link></Button>} />;
}
