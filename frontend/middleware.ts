import { NextResponse } from 'next/server';
import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server';
import { CLERK_MIDDLEWARE_OPTIONS } from '@/lib/clerkRoutes';

const isPublicRoute = createRouteMatcher([
  '/',
  '/privacy',
  '/sign-in(.*)',
  '/sign-up(.*)',
  '/api(.*)',
]);

const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

export default clerkEnabled
  ? clerkMiddleware(async (auth, request) => {
      if (!isPublicRoute(request)) {
        // Signed out: redirects to our /sign-in?redirect_url=<this page> (see CLERK_MIDDLEWARE_OPTIONS).
        await auth.protect();
      }
    }, CLERK_MIDDLEWARE_OPTIONS)
  : function middleware() {
      return NextResponse.next();
    };

export const config = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)',
  ],
};
