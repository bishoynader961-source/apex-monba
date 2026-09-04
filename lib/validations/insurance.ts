import { z } from 'zod';

export const insurancePlanSchema = z.object({
  plan_name: z.string().min(1, 'Plan name is required'),
  plan_code: z.string().optional().or(z.literal('')),
  carrier_id: z.string().min(1, 'Carrier ID is required'),
  group_number: z.string().default(''),
  bin: z.string().default(''),
  pcn: z.string().default(''),
  plan_type: z.string().default('COMMERCIAL'),
  active: z.number().default(1),
  copay_tier: z.string().default('1'),
  copay_amount: z.string().default('0.00'),
  help_desk_phone: z.string().optional().or(z.literal('')),
  fax_number: z.string().optional().or(z.literal('')),
  alt_phone: z.string().optional().or(z.literal('')),
  contact_name: z.string().optional().or(z.literal('')),
  address_line1: z.string().optional().or(z.literal('')),
  address_line2: z.string().optional().or(z.literal('')),
  city: z.string().optional().or(z.literal('')),
  state: z.string().optional().or(z.literal('')),
  zip: z.string().optional().or(z.literal('')),
  standard_copay: z.string().default('0.00'),
  co_insurance_pct: z.string().default('0.00'),
  deductible: z.string().default('0.00'),
  ncpcp_copay: z.string().default('0.00'),
  wc_copay: z.string().default('0.00'),
  pharmacy_verified: z.number().default(0),
  processor_id: z.string().optional().or(z.literal('')),
  notes: z.string().optional().or(z.literal('')),
});

export type InsurancePlanForm = z.infer<typeof insurancePlanSchema>;
