from fastapi import Depends, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from filzl import (
    APIException,
    ControllerBase,
    CoreDependencies,
    LinkAttribute,
    ManagedViewPath,
    Metadata,
    RenderBase,
    passthrough,
)
from filzl.database import DatabaseDependencies
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from filzl_auth.authorize import authorize_response
from filzl_auth.config import AuthConfig
from filzl_auth.dependencies import AuthDependencies
from filzl_auth.models import UserAuthMixin
from filzl_auth.views import get_auth_view_path


class LoginRequest(BaseModel):
    username: EmailStr
    password: str


class LoginInvalid(APIException):
    status_code = 401
    invalid_reason: str


class LoginRender(RenderBase):
    post_login_redirect: str


class LoginController(ControllerBase):
    """
    Clients can override this login controller to instantiate their own login / view conventions.
    """

    url = "/auth/login"
    view_path = (
        ManagedViewPath.from_view_root(get_auth_view_path(""), package_root_link=None)
        / "auth/login/page.tsx"
    )

    # Defaults to 24 hours
    token_expiration_minutes: int = 60 * 24

    def __init__(
        self,
        post_login_redirect: str,
    ):
        super().__init__()
        self.post_login_redirect = post_login_redirect

    async def render(
        self,
        request: Request,
        after_login: str | None = None,
        user: UserAuthMixin | None = Depends(AuthDependencies.peek_user),
    ) -> LoginRender:
        if user is not None:
            # return RedirectResponse(url=self.post_login_redirect, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
            return LoginRender(
                post_login_redirect="",
                metadata=Metadata(
                    explicit_response=RedirectResponse(
                        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                        url=after_login or self.post_login_redirect,
                    )
                ),
            )

        # Otherwise continue to load the initial page
        return LoginRender(
            post_login_redirect=after_login or self.post_login_redirect,
            metadata=Metadata(
                title="Login",
                links=[
                    LinkAttribute(rel="stylesheet", href="/static/auth_main.css"),
                ],
                ignore_global_metadata=True,
            ),
        )

    @passthrough(exception_models=[LoginInvalid])
    async def login(
        self,
        login_payload: LoginRequest,
        auth_config: AuthConfig = Depends(
            CoreDependencies.get_config_with_type(AuthConfig)
        ),
        session: AsyncSession = Depends(DatabaseDependencies.get_db_session),
    ):
        user_model = auth_config.AUTH_USER
        matched_users = select(user_model).where(
            user_model.email == login_payload.username
        )
        results = await session.execute(matched_users)
        user = results.scalars().first()
        if user is None:
            raise LoginInvalid(invalid_reason="User not found.")
        if not user.verify_password(login_payload.password):
            raise LoginInvalid(invalid_reason="Invalid password.")

        response = JSONResponse(content=[], status_code=status.HTTP_200_OK)
        response = authorize_response(
            response,
            user_id=user.id,
            auth_config=auth_config,
            token_expiration_minutes=self.token_expiration_minutes,
        )

        return response