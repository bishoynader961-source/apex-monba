import { z } from 'zod';

export const workersCompSchema = z.object({
  employer_name: z.string().min(1, 'Employer name is required'),
  claim_reference: z.string().min(1, 'Claim reference is required'),
  injury_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'Invalid date format (YYYY-MM-DD)'),
  carrier_id: z.string().min(1, 'Carrier ID is required'),
  pay_to_name: z.string().min(1, 'Pay-to name is required'),
  pay_to_address: z.string().min(1, 'Pay-to address is required'),
  // Additional fields from the existing model
  wc_carrier_name: z.string().optional(),
  wc_injury_description: z.string().optional(),
  employer_address: z.string().optional(),
  employer_phone: z.string().optional(),
  employer_phone_ext: z.string().optional(),
  employer_contact_name: z.string().optional(),
  employer_addr_line1: z.string().optional(),
  employer_addr_line2: z.string().optional(),
  employer_city: z.string().optional(),
  employer_state: z.string().optional(),
  employer_zip: z.string().optional(),
  pay_to_contact: z.string().optional(),
  pay_to_phone: z.string().optional(),
  pay_to_addr_line1: z.string().optional(),
  pay_to_addr_line2: z.string().optional(),
  pay_to_city: z.string().optional(),
  pay_to_state: z.string().optional(),
  pay_to_zip: z.string().optional(),
  status: z.enum(['open', 'pending_approval', 'approved', 'denied', 'closed']).optional(),
  notes: z.string().optional(),
});

export type WorkersCompForm = z.infer<typeof workersCompSchema>;