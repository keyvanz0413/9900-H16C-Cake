FROM node:20-alpine AS builder

WORKDIR /app

ARG NEXT_PUBLIC_USE_DEFAULT_AGENT=true
ARG NEXT_PUBLIC_DEFAULT_AGENT_NAME="Email Agent"

ENV NEXT_PUBLIC_USE_DEFAULT_AGENT=${NEXT_PUBLIC_USE_DEFAULT_AGENT}
ENV NEXT_PUBLIC_DEFAULT_AGENT_NAME=${NEXT_PUBLIC_DEFAULT_AGENT_NAME}

COPY package.json ./
RUN npm install

COPY . .
RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.ts ./next.config.ts

EXPOSE 3000

CMD ["npm", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
