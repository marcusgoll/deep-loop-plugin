---
name: deep-fullstack
description: Coordinate frontend+backend development with shared types. Use when building full-stack features, 'connect frontend to API', or 'end-to-end'. Includes E2E testing.
version: 9.0.0
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Task
---

# Deep Full-Stack - Coordinated Client/Server Development

When invoked, coordinate development across the entire stack with shared contracts and comprehensive E2E testing.

## The Full-Stack Mindset

1. **Contracts first** - Define the API contract before implementation
2. **Backend leads** - API implementation is the source of truth
3. **Types flow down** - Generate frontend types from backend
4. **E2E validates** - Integration tests verify the full flow

## Phase 1: Define Contracts

### API Contract Definition

Choose your contract approach:

**Option A: OpenAPI/Swagger**
```yaml
# openapi.yaml
openapi: 3.0.0
info:
  title: [API Name]
  version: 1.0.0
paths:
  /users:
    get:
      summary: List users
      responses:
        '200':
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/User'
components:
  schemas:
    User:
      type: object
      properties:
        id:
          type: string
        email:
          type: string
        name:
          type: string
```

**Option B: tRPC (TypeScript)**
```typescript
// src/server/routers/user.ts
import { z } from 'zod';
import { router, publicProcedure } from '../trpc';

export const userRouter = router({
  list: publicProcedure
    .query(async () => {
      return await db.users.findMany();
    }),
  create: publicProcedure
    .input(z.object({
      email: z.string().email(),
      name: z.string().min(1),
    }))
    .mutation(async ({ input }) => {
      return await db.users.create({ data: input });
    }),
});
```

**Option C: Shared Types (Monorepo)**
```typescript
// packages/shared/types/user.ts
export interface User {
  id: string;
  email: string;
  name: string;
  createdAt: Date;
}

export interface CreateUserInput {
  email: string;
  name: string;
}

export interface UserResponse {
  data: User;
}

export interface UsersListResponse {
  data: User[];
  pagination: {
    total: number;
    page: number;
    limit: number;
  };
}
```

### Error Codes Contract
```typescript
// packages/shared/errors.ts
export const ErrorCodes = {
  VALIDATION_ERROR: 'VALIDATION_ERROR',
  NOT_FOUND: 'NOT_FOUND',
  UNAUTHORIZED: 'UNAUTHORIZED',
  FORBIDDEN: 'FORBIDDEN',
  CONFLICT: 'CONFLICT',
  INTERNAL_ERROR: 'INTERNAL_ERROR',
} as const;

export interface ApiError {
  code: keyof typeof ErrorCodes;
  message: string;
  details?: Record<string, string[]>;
}
```

## Phase 2: Build Backend

### Implementation Order
1. Database schema/migrations
2. Models/entities
3. Business logic (services)
4. API routes/controllers
5. Validation middleware
6. Error handling

### Backend Checklist
- [ ] All endpoints match contract
- [ ] Request validation enforced
- [ ] Response shapes match types
- [ ] Error responses follow contract
- [ ] Unit tests pass
- [ ] Integration tests pass

### Generate Client Types
```bash
# From OpenAPI
npx openapi-typescript openapi.yaml --output src/types/api.ts

# From tRPC (automatic)
# Types are inferred from router

# From shared package (monorepo)
# Import directly: import { User } from '@myapp/shared'
```

## Phase 3: Build Frontend

### Implementation Order
1. API client setup
2. Type imports/generation
3. Data fetching hooks
4. UI components
5. Forms with validation
6. Error handling UI

### API Client Setup

**Fetch wrapper:**
```typescript
// src/lib/api.ts
import type { ApiError } from '@myapp/shared';

const API_BASE = process.env.NEXT_PUBLIC_API_URL;

export async function api<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const error: ApiError = await res.json();
    throw new ApiClientError(error);
  }

  return res.json();
}
```

**React Query hooks:**
```typescript
// src/hooks/useUsers.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { User, CreateUserInput } from '@myapp/shared';

export function useUsers() {
  return useQuery({
    queryKey: ['users'],
    queryFn: () => api<{ data: User[] }>('/users'),
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateUserInput) =>
      api<{ data: User }>('/users', {
        method: 'POST',
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
}
```

### Frontend Checklist
- [ ] Types imported from backend/shared
- [ ] API calls use typed client
- [ ] Loading states handled
- [ ] Error states handled
- [ ] Form validation matches backend
- [ ] Component tests pass

## Phase 4: Integration Testing

### E2E Test Setup

**Playwright:**
```typescript
// e2e/users.spec.ts
import { test, expect } from '@playwright/test';

test.describe('User Management', () => {
  test('can create a new user', async ({ page }) => {
    await page.goto('/users/new');

    await page.fill('[name="email"]', 'test@example.com');
    await page.fill('[name="name"]', 'Test User');
    await page.click('button[type="submit"]');

    await expect(page).toHaveURL('/users');
    await expect(page.locator('text=Test User')).toBeVisible();
  });

  test('shows validation errors', async ({ page }) => {
    await page.goto('/users/new');

    await page.click('button[type="submit"]');

    await expect(page.locator('text=Email is required')).toBeVisible();
    await expect(page.locator('text=Name is required')).toBeVisible();
  });
});
```

**Cypress:**
```typescript
// cypress/e2e/users.cy.ts
describe('User Management', () => {
  it('can create a new user', () => {
    cy.visit('/users/new');

    cy.get('[name="email"]').type('test@example.com');
    cy.get('[name="name"]').type('Test User');
    cy.get('button[type="submit"]').click();

    cy.url().should('include', '/users');
    cy.contains('Test User').should('be.visible');
  });
});
```

### Run E2E Tests
```bash
# Playwright
npx playwright test 2>&1

# Cypress
npx cypress run 2>&1
```

### E2E Checklist
- [ ] Happy path works end-to-end
- [ ] Form validation works
- [ ] Error handling works
- [ ] Navigation works
- [ ] Authentication flow works
- [ ] Data persists correctly

## Phase 5: Full-Stack Verification

### Coordination Checklist

**Type Safety:**
- [ ] No `any` types at API boundaries
- [ ] Request types match backend expectations
- [ ] Response types match frontend usage
- [ ] Error types handled consistently

**Data Flow:**
- [ ] Frontend sends correct request shape
- [ ] Backend validates and processes
- [ ] Backend returns correct response shape
- [ ] Frontend renders response correctly

**Error Handling:**
- [ ] Backend returns structured errors
- [ ] Frontend catches and displays errors
- [ ] Validation errors show field-level feedback
- [ ] Network errors handled gracefully

### Run Full Verification
```bash
# Start backend
npm run dev:backend &
BACKEND_PID=$!

# Wait for backend
sleep 5

# Start frontend
npm run dev:frontend &
FRONTEND_PID=$!

# Wait for frontend
sleep 5

# Run E2E tests
npm run test:e2e

# Cleanup
kill $BACKEND_PID $FRONTEND_PID
```

## Output Format

### Full-Stack Report

```markdown
# Full-Stack Integration Report

**Date**: [timestamp]
**Verdict**: [PASS | FAIL]

## Contract Verification

| Endpoint | Backend | Frontend | E2E |
|----------|---------|----------|-----|
| GET /users | PASS | PASS | PASS |
| POST /users | PASS | PASS | PASS |
| GET /users/:id | PASS | PASS | PASS |

## Type Safety

- Shared types: [Yes/No]
- Generated types: [Yes/No]
- No `any` at boundaries: [Yes/No]

## E2E Results

| Flow | Status | Details |
|------|--------|---------|
| User creation | PASS | [time] |
| User listing | PASS | [time] |
| Error handling | PASS | [time] |

## Issues Found

[List any integration issues]

## Recommendations

[Cross-stack improvements]
```

## Integration with Deep Loop

When used within deep loop:
1. Create contract first (PLAN phase output)
2. Build backend, then frontend (BUILD phase)
3. Run full-stack verification (REVIEW phase)
4. Fix integration issues (FIX phase)
5. Verify E2E tests pass (completion criteria)
