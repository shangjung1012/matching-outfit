FROM node:22-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci \
    && sha256sum package-lock.json | cut -d ' ' -f 1 \
        > node_modules/.matching-outfit-package-lock.sha256

COPY . .
COPY docker-entrypoint.sh /usr/local/bin/frontend-entrypoint
RUN chmod +x /usr/local/bin/frontend-entrypoint

EXPOSE 5173

ENTRYPOINT ["frontend-entrypoint"]
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
