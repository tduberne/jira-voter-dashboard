FROM python:3.7

RUN mkdir /app/
WORKDIR /app/

COPY requirements.txt ./
RUN pip3 install -r requirements.txt
RUN pip3 install gunicorn

COPY app.py ./

EXPOSE 8050

CMD ["gunicorn", "-w", "1", "--pythonpath" , "/app/" , "-b" , ":8050" , "--access-logfile" , "-" , "--log-level" , "debug" , "app:app.server"]
