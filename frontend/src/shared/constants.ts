import type { Provider, Severity } from './api/types';
export const providers: Provider[] = ['aws', 'azure', 'gcp'];
export const severities: Severity[] = ['critical', 'high', 'medium', 'low'];
