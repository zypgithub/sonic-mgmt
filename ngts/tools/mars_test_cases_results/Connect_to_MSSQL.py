import pyodbc


class ConnectMSSQL:
    def __init__(self, server, database, username, password):
        self.server = server
        self.database = database
        self.username = username
        self.password = password
        self.cursor = None
        self.conn = None
        self.is_connected = False

    def __del__(self):
        if self.is_connected is True:
            self.disconnect_db()

    def connect_db(self):
        self.conn = pyodbc.connect(
            # Linux driver, requires the ngts to have DSN "MSSQLDRIVERDSN" in /etc/odbc.ini
            # to be set up with the correct driver version, example:
            # echo -e '[MSSQLDRIVERDSN]\nDescription=Microsoft ODBC Driver 18 for SQL Server\nDriver=ODBC Driver 18 for SQL Server\n' | sudo tee -a /etc/odbc.ini
            'DSN=MSSQLDRIVERDSN;SERVER=' + self.server + ';DATABASE=' + self.database + ';UID=' + self.username + ';PWD=' + self.password)
        # Windows Driver
        # 'DRIVER={SQL Server Native Client 11.0};SERVER=' + self.server + ';DATABASE=' + self.database + ';UID=' + self.username + ';PWD=' + self.password)
        self.cursor = self.conn.cursor()
        self.is_connected = True

    def disconnect_db(self):

        if self.cursor is not None and self.is_connected is True:
            self.cursor.close()
        if self.conn is not None and self.is_connected is True:
            self.conn.close()
        self.is_connected = False

    def execute_db_cmd(self, cmd):
        self.cursor.execute(cmd)

    def get_or_insert_dim_id(self, get_query, insert_query):
        try:
            self.cursor.execute(get_query)
            result_id = self.cursor.fetchone()[0]
            return result_id
        except Exception as e:

            if "NoneType" in str(e):
                self.cursor.execute(insert_query)
                self.conn.commit()
                self.cursor.execute(get_query)
                result_id = self.cursor.fetchone()[0]
                return result_id

            else:
                raise Exception("SQL query: " + get_query + " failed. error: " + str(e))

    def query_insert(self, insert_query, get_query=None):
        try:
            self.cursor.execute(insert_query)
            self.conn.commit()

            if get_query is not None:
                self.cursor.execute(get_query)
                result_id = self.cursor.fetchone()[0]
                return result_id
            else:
                return None
        except Exception as e:
            raise Exception("SQL insert query: " + insert_query + " failed. error: " + str(e))

    def query_insert_return_la_table_id(self, insert_query):
        try:
            self.cursor.execute(insert_query)
            table_id = self.cursor.fetchone()[0]
            self.conn.commit()
            return table_id
        except Exception as e:
            raise Exception("SQL insert query: " + insert_query + " failed. error: " + str(e))

    def get_table_column_names(self, table_name):
        if not self.is_connected:
            self.connect_db()
            cmd = f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}';"
            self.cursor.execute(cmd)
            columns_query = self.cursor.fetchall()
            column_names = []
            for column in columns_query:
                column_names.append(column[0])
            return column_names

    def query_scalar(self, scalar_query):
        self.cursor.execute(scalar_query)
        result_id = self.cursor.fetchone()[0]
        return result_id

    @staticmethod
    def str_or_null(string):
        if len(string) <= 0:
            return 'null'
        else:
            return ("'" + string + "'")

    @staticmethod
    def object_or_null(object):
        if object is not None:
            return object
        else:
            return 'null'
