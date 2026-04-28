FROM node:18-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps

# Backend URLs are baked into the JS bundle at build time
ARG REACT_APP_API_URL
ARG REACT_APP_AIS_URL
ENV REACT_APP_API_URL=$REACT_APP_API_URL
ENV REACT_APP_AIS_URL=$REACT_APP_AIS_URL

COPY . .
RUN npm run build

FROM nginx:alpine

COPY --from=builder /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
