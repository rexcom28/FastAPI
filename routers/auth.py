import sys
sys.path.append("..")

from starlette.responses import RedirectResponse

from fastapi import Depends, HTTPException, status, APIRouter, Request, Response, Form
from pydantic import BaseModel, validator ,ValidationError
from typing import Optional
import models
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from database import SessionLocal, engine
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from datetime import datetime, timedelta
from jose import jwt, JWTError

from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from forms import UserCreate , LoginForm



SECRET_KEY = "KlgH6AzYDeZeGwD288to79I3vTHT8wp7"
ALGORITHM = "HS256"

templates = Jinja2Templates(directory="templates")

bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

models.Base.metadata.create_all(bind=engine)

oauth2_bearer = OAuth2PasswordBearer(tokenUrl="token")


router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    responses={401: {"user": "Not authorized"}}
)


def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


def get_password_hash(password):
    return bcrypt_context.hash(password)


def verify_password(plain_password, hashed_password):
    return bcrypt_context.verify(plain_password, hashed_password)


def authenticate_user(username: str, password: str, db):
    user = db.query(models.Users)\
        .filter(models.Users.username == username)\
        .first()

    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(username: str, user_id: int,
                        expires_delta: Optional[timedelta] = None):

    encode = {"sub": username, "id": user_id}
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    encode.update({"exp": expire})
    return jwt.encode(encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(request: Request):
    try:
        token = request.cookies.get("access_token")
        if token is None:
            return None
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user_id: int = payload.get("id")
        if username is None or user_id is None:
            logout(request)
        return {"username": username, "id": user_id}
    except JWTError:
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/token")
async def login_for_access_token(response: Response, form_data: OAuth2PasswordRequestForm = Depends(),
                                 db: Session = Depends(get_db)):
    user = authenticate_user(form_data.username, form_data.password, db)
    if not user:
        return False
    token_expires = timedelta(minutes=60)
    token = create_access_token(user.username,
                                user.id,
                                expires_delta=token_expires)

    response.set_cookie(key="access_token", value=token, httponly=True)

    return True


@router.get("/", response_class=HTMLResponse)
async def authentication_page(request: Request):
    
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/", response_class=HTMLResponse)
async def login(request: Request, db: Session = Depends(get_db)):
    try:
        form = LoginForm(request)
        await form.create_oauth_form()
        response = RedirectResponse(url="/todos", status_code=status.HTTP_302_FOUND)

        validate_user_cookie = await login_for_access_token(response=response, form_data=form, db=db)

        if not validate_user_cookie:
            msg = "Incorrect Username or Password"
            return templates.TemplateResponse("login.html", {"request": request, "msg": msg})
        return response
        
    except HTTPException:
        msg = "Unknown Error"
        return templates.TemplateResponse("login.html", {"request": request, "msg": msg})


@router.get("/logout")
async def logout(request: Request):
    msg = "Logout Successful"
    response = templates.TemplateResponse("login.html", {"request": request, "msg": msg})
    response.delete_cookie(key="access_token")
    return response

class UserCreate2(BaseModel):
    email: str = Form(...)
    username: str = Form(...,min_length=5)
    firstname: str
    lastname: str
    password: str = Form(..., min_length=6)
    password2: str
    @validator("firstname")
    def validate_firstname(cls,value):
        if 'frank' not in value:
            raise ValueError("no es el nombre correcto")
        return value

@router.get("/register", response_class=HTMLResponse)
async def register(request: Request):
   
    return templates.TemplateResponse("register.html", {"request": request})


@router.post("/register", response_class=HTMLResponse)
async def register_user(request: Request,                        
                        db: Session = Depends(get_db)):
    
    form2 = UserCreate(request)
    await form2.getFormfromRequest()
    
    es:bool=False
    err:{}

    try:
        form = UserCreate2.model_validate(await request.form())        
        
    except ValidationError as e:
        es=True
        err=e
        
        pass
    if es:
        
        error_messages = [f"{error['loc'][0]}: {error['msg']}" for error in err.errors()]
        
        #msg = "Errores en la solicitud de registro:\n" + "\n".join(error_messages)
        return templates.TemplateResponse("register.html", {"request": request, "err": error_messages, "form2": form2 })

    validation1 = db.query(models.Users).filter(models.Users.username == form.username).first()

    validation2 = db.query(models.Users).filter(models.Users.email == form.email).first()
    
    if form.password != form.password2 or validation1 is not None or validation2 is not None:
        msg = "Invalid registration request \n" 
        if validation1:
            msg += f"-El nombre de usuario: '{form.username}' ya existe"
        if validation2:
            msg+= f"-El email: {form.email} ya existe \n"    
        return templates.TemplateResponse("register.html", {"request": request, "msg": msg, "form2": form2 })

    user_model = models.Users()
    user_model.username = form.username
    user_model.email = form.email
    user_model.first_name = form.firstname
    user_model.last_name = form.lastname

    hash_password = get_password_hash(form.password)
    user_model.hashed_password = hash_password
    user_model.is_active = True

    db.add(user_model)
    db.commit()

    msg = "User successfully created"
    return templates.TemplateResponse("login.html", {"request": request, "msg": msg})
