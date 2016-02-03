from sqlalchemy import Column, ForeignKey, Integer, String, Date, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Record(Base):
    __tablename__ = 'records'
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, nullable=False)
    locker_id = Column(Integer, nullable=False)
    date_in = Column(Date, nullable=False)
    date_out = Column(Date, nullable=True)
    checked_out = Column(Boolean)

# Index('my_index', MyModel.name, unique=True, mysql_length=255)