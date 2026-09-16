FROM node:20-alpine

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
ENV BACKEND_URL=http://backend:8000
EXPOSE 3000
CMD ["npm", "run", "dev"]
